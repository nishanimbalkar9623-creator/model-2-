"""Lightweight in-process metrics hooks.

Kept intentionally small — a hackathon-appropriate counter store that a
Prometheus exporter / metrics endpoint can read from later.
"""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from typing import Any, Dict

_counter_lock = threading.Lock()
_counter: Dict[str, int] = defaultdict(int)
_histogram: Dict[str, deque] = defaultdict(lambda: deque(maxlen=1000))


def incr(name: str, amount: int = 1) -> None:
    with _counter_lock:
        _counter[name] += amount


def observe(name: str, value: float) -> None:
    with _counter_lock:
        _histogram[name].append(value)


def record_turn(
    *,
    success: bool,
    latency_ms: float,
    model: str,
    tool_calls: int,
) -> None:
    incr("chat.turns.total", 1)
    incr("chat.turns.ok" if success else "chat.turns.error", 1)
    incr("chat.tool_calls", tool_calls)
    observe("chat.latency_ms", latency_ms)
    if model:
        incr(f"chat.model.{model}", 1)


def snapshot() -> Dict[str, Any]:
    with _counter_lock:
        return {
            "counters": dict(_counter),
            "histograms": {
                k: {"count": len(v), "sum": round(sum(v), 2)} for k, v in _histogram.items()
            },
        }
