"""Working memory / context manager.

Holds the current user, client, recent tool results, and any short-lived
state needed during one agent turn. Also covers working memory: current client,
current task, current workflow, current date/time.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.schemas.agent import ClientContext, UserContext


@dataclass
class WorkingMemory:
    user: UserContext = field(default_factory=UserContext)
    client: ClientContext = field(default_factory=ClientContext)
    current_task: Any = None
    current_workflow: str = ""
    recent_tool_results: List[Dict[str, Any]] = field(default_factory=list)

    def add_tool_result(self, tool_name: str, result: Any) -> None:
        self.recent_tool_results.append({"tool": tool_name, "result": result})
        if len(self.recent_tool_results) > 10:
            self.recent_tool_results = self.recent_tool_results[-10:]


class ContextManager:
    def __init__(self) -> None:
        self.user: UserContext = UserContext()
        self.client: ClientContext = ClientContext()
        self.memory: WorkingMemory = WorkingMemory()
        self.recent_tool_results: List[Dict[str, Any]] = []

    def set_user(self, user_id: Optional[str] = None, user_role: Optional[str] = None) -> None:
        self.user = UserContext(user_id=user_id, user_role=user_role)
        self.memory.user = self.user

    def set_client(self, client: Optional[ClientContext] = None) -> None:
        if client is not None:
            self.client = client
            self.memory.client = client

    def record_tool_result(self, name: str, result: Any) -> None:
        self.memory.add_tool_result(name, result)
        self.recent_tool_results.append({"tool": name, "result": result})
        if len(self.recent_tool_results) > 10:
            self.recent_tool_results = self.recent_tool_results[-10:]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "user": self.user.model_dump(exclude_none=True),
            "client": self.client.model_dump(exclude_none=True),
        }

    def as_dict(self) -> Dict[str, Any]:
        return self.to_dict()
