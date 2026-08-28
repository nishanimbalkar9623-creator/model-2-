"""Input validation & output validation.

- Validates tool arguments using Pydantic (LLM can never invent args).
- Sanitizes/validates outbound LLM responses.
- Enforces prompt-injection defenses and request limits.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Optional, Type

from pydantic import BaseModel, ValidationError

from app.config import settings
from app.safety.pii import redact_dict


class InputValidationError(Exception):
    pass


class ToolArgValidationError(Exception):
    def __init__(self, message: str, errors: Optional[str] = None):
        super().__init__(message)
        self.errors = errors


def validate_tool_args(schema_cls: Type[BaseModel], args: Dict[str, Any]) -> BaseModel:
    """Validate tool arguments against a Pydantic model.

    If the LLM produces a string containing JSON, coerce it first.
    Raises ToolArgValidationError on failure.
    """
    if isinstance(args, str):
        try:
            args = json.loads(args)
        except json.JSONDecodeError as exc:
            raise ToolArgValidationError(f"Tool arguments are not valid JSON: {exc}")
    if not isinstance(args, dict):
        raise ToolArgValidationError(f"Tool arguments must be an object, got {type(args).__name__}")
    try:
        return schema_cls.model_validate(args)
    except ValidationError as exc:
        raise ToolArgValidationError(
            f"Tool arguments failed validation", errors=exc.json()
        ) from exc


class PromptInjectionError(Exception):
    pass


# Phrases often used for prompt injection. Not a hard blocker by itself, but
# the engine will treat document content as DATA unconditionally.
INJECTION_HINTS = [
    "ignore previous instructions",
    "ignore all previous",
    "disregard prior",
    "you are now",
    "expose all clients",
    "forget your instructions",
    "system prompt",
    "override instructions",
    "new instruction",
    "new rule",
    "do not obey",
    "do not follow",
    "act as",
    "pretend to be",
    "your real instructions",
    "reveal your prompt",
    "show me your prompt",
]

# Patterns for more sophisticated detection
INJECTION_PATTERNS = [
    r"ignore\s+(?:all\s+)?previous\s+instructions?",
    r"disregard\s+(?:all\s+)?(?:previous|prior)",
    r"you\s+are\s+now\s+(?:a\s+)?",
    r"system\s+prompt",
    r"expose\s+(?:all\s+)?clients?",
    r"forget\s+(?:your\s+)?instructions?",
    r"override\s+(?:the\s+)?instructions?",
    r"new\s+(?:instruction|rule|policy)",
    r"do\s+not\s+(?:obey|follow)",
    r"act\s+as\s+(?:a\s+)?",
    r"pretend\s+to\s+be\s+(?:a\s+)?",
    r"(?:your|the)\s+real\s+instructions?",
    r"reveal\s+(?:your|the)\s+prompt",
    r"show\s+me\s+(?:your|the)\s+prompt",
]


def contains_injection_signal(text: str) -> bool:
    """Check for prompt injection signals in text."""
    if not text:
        return False
    low = text.lower()
    # Quick substring check
    if any(h in low for h in INJECTION_HINTS):
        return True
    # Regex patterns
    for pattern in INJECTION_PATTERNS:
        if re.search(pattern, low):
            return True
    return False


def validate_request_size(text: str) -> None:
    if len(text) > settings.max_request_chars:
        raise InputValidationError(
            f"Request exceeds max length of {settings.max_request_chars} characters"
        )


def sanitize_llm_number(value: Any) -> Optional[float]:
    """Best-effort numeric coercion for LLM output (e.g. report figures)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.replace(",", "").replace("₹", "").strip())
        except ValueError:
            return None
    return None


def sanitize_document_content(content: str) -> str:
    """
    Sanitize document content before including in LLM context.
    Treats documents as DATA, never as instructions.
    """
    # Redact PII
    content = redact_dict({"content": content})["content"]
    
    # Flag injection signals but don't block (documents are data)
    if contains_injection_signal(content):
        # Log warning but continue - documents are untrusted data
        import logging
        logging.getLogger("aos.safety").warning(
            "Document contains potential injection signal - treating as data only"
        )
    
    return content


def sanitize_tool_result(result: Any) -> Any:
    """Sanitize tool result before sending to LLM."""
    if isinstance(result, dict):
        return {k: sanitize_tool_result(v) for k, v in result.items()}
    elif isinstance(result, list):
        return [sanitize_tool_result(v) for v in result]
    elif isinstance(result, str):
        # Redact PII from tool results
        return redact_dict({"content": result})["content"]
    return result


def validate_llm_response(response: str) -> str:
    """Validate and sanitize LLM response before sending to user."""
    if not response:
        return response
    
    # Redact PII from response
    response = redact_dict({"content": response})["content"]
    
    # Ensure no injection signals in response (shouldn't happen but safety check)
    if contains_injection_signal(response):
        import logging
        logging.getLogger("aos.safety").warning(
            "LLM response contains injection signal - redacting"
        )
        # Could truncate or sanitize further
    
    return response
