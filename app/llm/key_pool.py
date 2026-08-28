"""OpenRouter key pool manager.

Loads multiple API keys from the environment (``OPENROUTER_API_KEY_1..N``),
validates them, and hands them out in a concurrency-safe round-robin fashion.
Keys that fail temporary errors (429, 5xx, timeout) are temporarily marked
unavailable and recover after a cooldown. Keys that fail auth (401/403) are
held out for a much longer window.

Security: this module never logs, prints, returns or serializes raw key
material. Diagnostics use a masked representation (e.g. ``sk-or-v1-****abcd``)
and an integer index.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from typing import Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger("aos.openrouter.keypool")

# Prefixes we may see on OpenRouter keys, used purely for masking.
_KEY_PREFIXES = ("sk-or-", "sk-or-v1-", "sk-")


def mask_key(key: Optional[str]) -> str:
    """Return a masked representation of a key; never the full value."""
    if not key:
        return "<none>"
    # Show a short stable suffix only — insufficient to reconstruct/auth.
    tail = key[-4:] if len(key) >= 4 else key
    return f"****{tail}"


def _cooldown_for(kind: str, base: float) -> float:
    """Cooldown seconds for a given failure kind."""
    if kind in ("auth", "403", "401"):
        # Invalid/disabled key — hold out for a long time (until reload).
        return max(base, 3600.0)
    if kind == "429":
        return max(base, 0.1)
    # 5xx / timeout / connectivity
    return max(base, 0.1)


class _KeySlot:
    __slots__ = ("index", "key", "available_after", "disabled_until", "last_error")

    def __init__(self, index: int, key: str):
        self.index = index  # 1-based, matches OPENROUTER_API_KEY_N
        self.key = key
        self.available_after: float = 0.0
        self.disabled_until: float = 0.0
        self.last_error: Optional[str] = None

    @property
    def is_available(self) -> bool:
        return time.monotonic() >= max(self.available_after, self.disabled_until)


class OpenRouterKeyPool:
    """Concurrency-safe pool of OpenRouter API keys with cooldown logic."""

    def __init__(
        self,
        cooldown_seconds: Optional[float] = None,
        keys: Optional[List[str]] = None,
    ):
        self.cooldown_seconds = float(
            cooldown_seconds
            if cooldown_seconds is not None
            else settings.openrouter_key_cooldown_seconds
        )
        raw_keys = keys if keys is not None else self._load_keys_from_env()
        self._slots: List[_KeySlot] = []
        for idx, raw in enumerate(raw_keys, start=1):
            key = (raw or "").strip()
            if not key or key.startswith("PASTE_"):
                continue
            self._slots.append(_KeySlot(idx, key))

        self._cursor = 0
        self._lock = asyncio.Lock()

    # ---- Loading ----

    @staticmethod
    def _load_keys_from_env() -> List[str]:
        keys: List[str] = []
        i = 1
        while True:
            val = os.environ.get(f"OPENROUTER_API_KEY_{i}")
            if val is None:
                break
            keys.append(val)
            i += 1
        # Support single key as a safe convenience too.
        if not keys:
            single = os.environ.get("OPENROUTER_API_KEY")
            if single:
                keys.append(single)
        return keys

    # ---- Introspection ----

    @property
    def total(self) -> int:
        return len(self._slots)

    @property
    def healthy(self) -> int:
        return sum(1 for s in self._slots if s.is_available)

    def has_keys(self) -> bool:
        return len(self._slots) > 0

    def masked_keys(self) -> List[str]:
        """Masked snapshot for diagnostics (never raw keys)."""
        return [mask_key(s.key) for s in self._slots]

    def health(self) -> Dict[str, object]:
        return {
            "configured_keys": self.total,
            "healthy_keys": self.healthy,
            "temporarily_disabled": self.total - self.healthy,
            "cooldown_seconds": self.cooldown_seconds,
        }

    # ---- Selection ----

    async def acquire_healthy(self) -> Optional[_KeySlot]:
        """Return an available key slot, or None if none are healthy."""
        async with self._lock:
            slots = self._slots
            if not slots:
                return None
            start = self._cursor
            for _ in range(len(slots)):
                slot = slots[self._cursor % len(slots)]
                self._cursor += 1
                if slot.is_available:
                    return slot
                # stop after a full circular scan
                if (self._cursor % len(slots)) == start % len(slots) and self._cursor > start:
                    break
            return None

    def _any_available_without_lock(self) -> bool:
        return any(s.is_available for s in self._slots)

    async def next_healthy_index(self) -> Optional[int]:
        slot = await self.acquire_healthy()
        return slot.index if slot else None

    # ---- Failure recording ----

    def mark_failure(self, index: int, kind: str, retry_after: Optional[float] = None) -> None:
        """Record a failure for a key and apply the appropriate cooldown."""
        for slot in self._slots:
            if slot.index == index:
                now = time.monotonic()
                slot.last_error = kind
                if kind in ("401", "403", "auth"):
                    slot.disabled_until = now + _cooldown_for("auth", self.cooldown_seconds)
                    slot.available_after = now
                else:
                    cd = _cooldown_for(kind, self.cooldown_seconds)
                    if retry_after is not None and retry_after > 0:
                        cd = min(cd, max(retry_after, 1))
                    slot.available_after = now + cd
                    slot.disabled_until = now
                logger.info("OpenRouter key %d marked unavailable (%s)", index, kind)
                return

    def mark_recovered(self, index: int) -> None:
        """Explicitly re-enable a key (e.g. after a successful call)."""
        for slot in self._slots:
            if slot.index == index:
                slot.available_after = 0.0
                slot.disabled_until = 0.0
                slot.last_error = None
                return

    def has_available(self) -> bool:
        return self._any_available_without_lock()

    async def force_refresh(self) -> None:
        """Re-check availability (mostly for tests / diagnostics)."""
        async with self._lock:
            return None
