"""Context variables shared across the request lifecycle (request_id etc.)."""

from __future__ import annotations

from contextvars import ContextVar
from typing import Optional

request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
conversation_id_var: ContextVar[Optional[str]] = ContextVar(
    "conversation_id", default=None
)
user_id_var: ContextVar[Optional[str]] = ContextVar("user_id", default=None)
client_id_var: ContextVar[Optional[str]] = ContextVar("client_id", default=None)
