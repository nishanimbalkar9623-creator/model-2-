"""Agent state machine definition."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.agent import ClientContext, IntentType, UserContext


@dataclass
class AgentState:
    intent: IntentType = IntentType.UNKNOWN
    user: UserContext = field(default_factory=UserContext)
    client: ClientContext = field(default_factory=ClientContext)
    message: str = ""
    conversation_id: str = ""
    tools_to_run: List[str] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    plan: List[str] = field(default_factory=list)
    sources: List[Dict[str, Any]] = field(default_factory=list)
    pending_confirmation: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    reply: str = ""

    def to_snapshot(self) -> Dict[str, Any]:
        return {
            "intent": self.intent.value,
            "user": {"id": self.user.user_id, "role": self.user.user_role},
            "client_id": self.client.client_id,
            "client_name": self.client.client_name,
            "tools_to_run": self.tools_to_run,
            "has_pending_confirmation": self.pending_confirmation is not None,
            "error": self.error,
        }
