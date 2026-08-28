"""Tool executor with safety:
- validates args via Pydantic
- enforces permissions + client isolation
- checks confirmation policy
- executes via BackendClient
- catches backend errors and converts them to AI-safe messages
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from app.backend.client import BackendClient
from app.llm.base import LLMProvider
from app.memory.context import ContextManager
from app.safety.permissions import (
    PermissionDenied,
    assert_client_access,
    check_tool_allowed,
)
from app.schemas.agent import ClientContext, UserContext
from app.schemas.tools import ToolResult, ToolStatus
from app.tools.registry import ToolRegistry, get_registry


class ToolExecutionPlan:
    def __init__(
        self,
        *,
        backend: BackendClient,
        user: UserContext,
        client: ClientContext,
        context: ContextManager,
        llm: Optional[LLMProvider] = None,
        conversation_id: Optional[str] = None,
    ):
        self.backend = backend
        self.user = user
        self.client = client
        self.context = context
        self.llm = llm
        self.conversation_id = conversation_id
        self.registry: ToolRegistry = get_registry()

    def _accessible_clients(self) -> Optional[List[str]]:
        rank = (self.user.user_role or "").lower()
        if rank in {"admin", "partner", "manager"}:
            return None  # let backend decide; it will 403 if not allowed
        return [self.client.client_id] if self.client.client_id else []

    def plan_tool_calls(self, intent) -> List[str]:
        mapping = {
            "general": ["list_clients"],
            "client_specific": ["get_client_status", "get_pending_work"],
            "data_analysis": ["get_reconciliation_summary", "get_reconciliation_exceptions"],
            "report": ["generate_client_report"],
            "action": ["create_task"],
            "unknown": [],
        }
        intent_str = intent.value if hasattr(intent, "value") else str(intent)
        tools = mapping.get(intent_str, [])
        return tools if tools else []

    async def execute(
        self,
        tool_name: str,
        args: Dict[str, Any] = None,
        *,
        explicit_intent: bool = False,
        request_id: Optional[str] = None,
    ) -> ToolResult:
        args = args or {}
        tool = self.registry.get(tool_name)
        if tool is None:
            return ToolResult(
                name=tool_name,
                status=ToolStatus.ERROR,
                error=f"Unknown tool '{tool_name}'",
            )

        # 1. permission boundary
        try:
            check_tool_allowed(tool.descriptor, self.user)

            # 2. client isolation
            cid = args.get("client_id") or self.client.client_id
            accessible = self._accessible_clients()
            if cid:
                assert_client_access(cid, self.user, accessible)
        except PermissionDenied as exc:
            return ToolResult(name=tool_name, status=ToolStatus.BLOCKED, error=str(exc))

        # 3. pydantic validation
        try:
            validated = tool.input_model.model_validate(args)
        except Exception as exc:
            return ToolResult(
                name=tool_name,
                status=ToolStatus.ERROR,
                error=f"Invalid arguments: {exc}",
            )

        args_dict = validated.model_dump()

        # 3.5 confirmation gate — mutating/high-risk tools need explicit approval
        from app.agent.confirmation import create_confirmation_gate
        from app.safety.action_policy import requires_confirmation

        if requires_confirmation(
            tool.descriptor,
            explicit_intent=explicit_intent,
        ) and not explicit_intent:
            if self.conversation_id:
                create_confirmation_gate(
                    self.conversation_id,
                    tool_name,
                    args_dict,
                    requires_confirmation=True,
                )
            return ToolResult(
                name=tool_name,
                status=ToolStatus.NEEDS_CONFIRMATION,
                error=(
                    f"Action '{tool_name}' requires your confirmation. "
                    "Use POST /api/v1/chat/confirm to approve it."
                ),
            )

        # 4. Execute
        try:
            data = await tool.execute(
                args_dict,
                backend=self.backend,
                user_id=self.user.user_id,
                user_role=self.user.user_role,
            )
            self.context.record_tool_result(tool_name, data)
            return ToolResult(name=tool_name, status=ToolStatus.OK, data=data)
        except Exception as exc:
            if hasattr(exc, "status_code") and exc.status_code == 403:
                return ToolResult(name=tool_name, status=ToolStatus.BLOCKED, error=str(exc))
            return ToolResult(
                name=tool_name,
                status=ToolStatus.ERROR,
                error=f"Backend rejected: {type(exc).__name__}: {exc}",
            )
