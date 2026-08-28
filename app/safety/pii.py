"""PII detection/redaction helpers for CA financial data.

Used to keep sensitive info (PAN, Aadhaar, account numbers, phone) out of
logs and out of outbound responses unless the user legitimately needs it.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

# Indian identifiers / financial sensitive patterns
_PATTERNS = [
    (r"\b[A-Z]{5}[0-9]{4}[A-Z]\b", "PAN"),                 # PAN
    (r"\b[2-9][0-9]{11}\b", "AADHAAR"),                    # Aadhaar (12 digit, valid first digit)
    (r"\b\d{10}\b", "PHONE"),                              # 10-digit phone
    (r"\b\d{9,18}\b", "ACCOUNT_NUMBER"),                   # bank account
    (r"\b\d{13,19}\b", "CARD"),                            # card-ish
    (r"\b[A-Z]{3}[0-9]GSTIN[0-9A-Z]{4,}\b", "GSTIN_PARTIAL"),
]


def detect_pii(text: str) -> List[Tuple[str, str]]:
    """Return list of (category, matched_fragment)."""
    found: List[Tuple[str, str]] = []
    for pattern, label in _PATTERNS:
        for m in re.finditer(pattern, text):
            found.append((label, m.group(0)))
    return found


def redact_pii(text: str) -> str:
    """Replace sensitive fragments with a masked placeholder."""
    for pattern, label in _PATTERNS:
        text = re.sub(pattern, f"[{label}_REDACTED]", text)
    return text


def redact_dict(value: Any) -> Any:
    """Recursively redact PII in a nested structure (for logging/response)."""
    if isinstance(value, dict):
        return {k: redact_dict(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_dict(v) for v in value]
    if isinstance(value, str):
        return redact_pii(value)
    return value


SENSITIVE_FIELD_NAMES = {
    "pan", "aadhaar", "aadhar", "account_number", "bank_account", "ifsc",
    "phone", "mobile", "card", "cvv", "bank_details",
}


def contains_sensitive_fields(data: Dict[str, Any]) -> bool:
    for key in data:
        if key.lower() in SENSITIVE_FIELD_NAMES:
            return True
    return False
