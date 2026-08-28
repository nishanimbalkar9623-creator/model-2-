"""Formal tool registry.

Each tool has:
- name
- description
- Pydantic input schema (JSON schema provided for the LLM)
- permission requirement
- read-only vs mutating
- requires_confirmation / destructive

Tools call the Backend (authoritative) via BackendClient.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional, Type

from pydantic import BaseModel

from app.backend.client import BackendClient
from app.llm.base import ToolSpec
from app.schemas.tools import PermissionLevel, ToolDescriptor, ToolKind


class ToolDefinition:
    def __init__(
        self,
        name: str,
        description: str,
        input_model: Type[BaseModel],
        kind: ToolKind,
        *,
        permission: PermissionLevel = PermissionLevel.VIEW,
        requires_confirmation: bool = False,
        destructive: bool = False,
        handler: Optional[Callable[..., Any]] = None,
    ):
        self.name = name
        self.description = description
        self.input_model = input_model
        self.kind = kind
        self.permission = permission
        self.requires_confirmation = requires_confirmation
        self.destructive = destructive
        self.handler = handler

    @property
    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            name=self.name,
            description=self.description,
            parameters_schema=self.input_model.model_json_schema(),
            kind=self.kind,
            permission=self.permission,
            requires_confirmation=self.requires_confirmation,
            destructive=self.destructive,
        )

    def to_llm_spec(self) -> ToolSpec:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.input_model.model_json_schema(),
        )

    async def execute(
        self,
        args: Dict[str, Any],
        *,
        backend: BackendClient,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
    ) -> Any:
        """Execute the tool. Default handler hits the backend path for the tool name."""
        from app.backend.endpoints import get_endpoint
        
        path = get_endpoint(self.name)
        data = await backend.post(
            path, json=args, user_id=user_id, user_role=user_role
        )
        return data


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: Dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.name] = tool

    def get(self, name: str) -> Optional[ToolDefinition]:
        return self._tools.get(name)

    def all(self) -> List[ToolDefinition]:
        return list(self._tools.values())

    def descriptors(self) -> List[ToolDescriptor]:
        return [t.descriptor for t in self._tools.values()]

    def specs(self) -> List[ToolSpec]:
        return [t.to_llm_spec() for t in self._tools.values()]


_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
        _register_default_tools(_registry)
    return _registry


def _register_default_tools(reg: ToolRegistry) -> None:
    from app.tools.client_tools import register_client_tools
    from app.tools.document_tools import register_document_tools
    from app.tools.workflow_tools import register_workflow_tools
    from app.tools.task_tools import register_task_tools
    from app.tools.meeting_tools import register_meeting_tools
    from app.tools.report_tools import register_report_tools
    from app.tools.reconciliation_tools import register_reconciliation_tools
    from app.tools.search_tools import register_search_tools

    register_client_tools(reg)
    register_document_tools(reg)
    register_workflow_tools(reg)
    register_task_tools(reg)
    register_meeting_tools(reg)
    register_report_tools(reg)
    register_reconciliation_tools(reg)
    register_search_tools(reg)
