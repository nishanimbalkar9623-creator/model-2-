"""Conversation memory — short-term (current conversation) with TTL and cap.

Deliberately independent of any SQL backend to keep the footprint small.
A TTL cache keyed by conversation_id. The engine decides what is relevant
rather than blindly sending everything to the LLM forever.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from app.config import settings


@dataclass
class Conversation:
    conversation_id: str = field(default_factory=lambda: f"conv_{uuid.uuid4().hex[:8]}")
    user_id: Optional[str] = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)
    pending_action: Optional[Dict[str, Any]] = None

    def to_prompt_messages(self) -> List[Dict[str, Any]]:
        return self.messages[-settings.memory_max_messages :]


_TTL = threading.local()


class ConversationMemory:
    def __init__(self, ttl_seconds: Optional[int] = None):
        self._store: Dict[str, Conversation] = {}
        self._lock = threading.RLock()
        self._ttl = ttl_seconds or settings.memory_ttl_seconds

    def get_or_create(self, conversation_id: Optional[str], user_id: Optional[str] = None) -> Conversation:
        with self._lock:
            self._gc()
            if conversation_id and conversation_id in self._store:
                return self._store[conversation_id]
            conv = Conversation(user_id=user_id)
            # preserve caller's id if given, otherwise generate a fresh one
            if conversation_id:
                conv.conversation_id = conversation_id
            self._store[conv.conversation_id] = conv
            return conv

    def add_turn(
        self,
        conversation_id: str,
        message: Dict[str, Any],
    ) -> None:
        with self._lock:
            conv = self.get_or_create(conversation_id)
            conv.messages.append(message)
            if len(conv.messages) > settings.memory_max_messages:
                conv.messages = conv.messages[-settings.memory_max_messages :]

    def get(self, conversation_id: str) -> Optional[Conversation]:
        with self._lock:
            self._gc()
            return self._store.get(conversation_id)

    def set_pending_action(self, conversation_id: str, action: Dict[str, Any]) -> None:
        with self._lock:
            conv = self.get_or_create(conversation_id)
            conv.pending_action = action

    def get_pending_action(self, conversation_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            conv = self.get(conversation_id)
            return conv.pending_action if conv else None

    def clear_pending_action(self, conversation_id: str) -> None:
        with self._lock:
            conv = self.get(conversation_id)
            if conv:
                conv.pending_action = None

    def clear(self) -> None:
        with self._lock:
            self._store.clear()

    def _gc(self) -> None:
        # simple TTL-based cleanup
        now = time.time()
        expired = [
            cid for cid, conv in self._store.items() if (now - conv.created_at) > self._ttl
        ]
        for cid in expired:
            del self._store[cid]


_memory: Optional[ConversationMemory] = None


def get_conversation_memory() -> ConversationMemory:
    global _memory
    if _memory is None:
        _memory = ConversationMemory()
    return _memory
