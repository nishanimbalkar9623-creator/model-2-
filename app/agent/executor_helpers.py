"""Simple injection-signal detection (best-effort heuristic). The real defense
is treating document content as DATA, never as instructions."""

from __future__ import annotations

import re
from typing import Any, Dict


INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions",
    r"disregard\s+(?:all\s+)?previous",
    r"you\s+are\s+now",
    r"system\s+prompt",
    r"expose\s+(?:all\s+)?clients",
    r"(?:new|changed)\s+(?:instruction|rule|policy)",
    r"do\s+not\s+(?:obey|follow)",
]


def contains_injection_signal(text: str) -> bool:
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True
    return False


def redact_dict(data: Dict[str, Any]) -> Dict[str, Any]:
    RESERVED = {
        "api_key", "token", "secret", "password", "authorization",
        "pan", "aadhaar", "account_number", "cvv", "otp", "bank_details",
    }
    out = {}
    for k, v in data.items():
        if isinstance(v, dict):
            out[k] = redact_dict(v)
        elif isinstance(v, (list, tuple)):
            out[k] = [redact_dict(x) if isinstance(x, dict) else x for x in v]
        elif isinstance(v, str) and k.lower() in RESERVED:
            out[k] = "***"
        else:
            out[k] = v
    return out
