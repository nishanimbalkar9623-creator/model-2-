"""Structured, provider-independent LLM exceptions.

The rest of the application should only ever see these classes, never
raw vendor error payloads or API keys. All exceptions are safe to surface
in logs because they never contain secret material (keys are masked before
being attached).
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class LLMError(Exception):
    """Base class for all LLM errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: Optional[int] = None,
        retryable: bool = False,
        details: Optional[Dict[str, Any]] = None,
    ):
        self.message = message
        self.status_code = status_code
        self.retryable = retryable
        self.details = details or {}
        super().__init__(message)


class LLMAuthenticationError(LLMError):
    """Invalid/disabled API key (401/403)."""

    def __init__(self, message: str = "LLM authentication failed", **kw: Any):
        super().__init__(message, retryable=False, **kw)


class LLMRateLimitError(LLMError):
    """Provider rate limit exhausted (429)."""

    def __init__(self, message: str = "LLM rate limit exceeded", **kw: Any):
        super().__init__(message, retryable=True, **kw)


class LLMTimeoutError(LLMError):
    """Request timed out; safe to retry on another key."""

    def __init__(self, message: str = "LLM request timed out", **kw: Any):
        super().__init__(message, retryable=True, **kw)


class LLMProviderError(LLMError):
    """Generic provider failure (5xx, connection errors, etc.).

    ``retryable`` is set based on whether retrying is likely to help.
    """

    def __init__(self, message: str = "LLM provider error", **kw: Any):
        super().__init__(message, **kw)


class LLMInvalidRequestError(LLMError):
    """A 400-class problem: bad model, invalid schema, malformed request.

    Not retryable — blindly retrying will not fix it.
    """

    def __init__(self, message: str = "Invalid LLM request", **kw: Any):
        super().__init__(message, retryable=False, **kw)


class LLMUnavailableError(LLMError):
    """No healthy keys remain or provider is unavailable; retryable."""

    def __init__(self, message: str = "LLM service unavailable", **kw: Any):
        super().__init__(message, retryable=True, **kw)
