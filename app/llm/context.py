"""Context / token control helpers.

AOS can hold large client datasets. Before content reaches any LLM provider
we truncate large tool results and document extracts to a bounded size so we
never blindly forward whole spreadsheets or huge blobs to the model. The heavy
data processing lives in the backend/ML layer; the LLM only sees structured,
bounded summaries and relevant exceptions.
"""

from __future__ import annotations

from typing import Any

# Default ceilings — tune via env if needed.
DEFAULT_MAX_CONTENT_CHARS = 8000
DEFAULT_MAX_TOOL_RESULT_CHARS = 4000
DEFAULT_MAX_DOCUMENT_CHARS = 6000


def truncate_text(
    text: str,
    max_chars: int = DEFAULT_MAX_CONTENT_CHARS,
    tail_chars: int = 400,
) -> str:
    """Truncate text keeping the head and a small tail, with a clear marker."""
    text = text or ""
    if len(text) <= max_chars:
        return text
    head = text[: max_chars - tail_chars]
    tail = text[-tail_chars:]
    return f"{head}\n...[truncated {len(text) - max_chars} chars]...\n{tail}"


def truncate_tool_result(data: Any, max_chars: int = DEFAULT_MAX_TOOL_RESULT_CHARS) -> str:
    """Serialize a tool result to a bounded string safe for LLM context."""
    if data is None:
        return "None"
    if not isinstance(data, str):
        try:
            import json

            data = json.dumps(data, default=str)
        except Exception:
            data = str(data)
    return truncate_text(data, max_chars)


def truncate_document(content: str, max_chars: int = DEFAULT_MAX_DOCUMENT_CHARS) -> str:
    """Truncate an extracted document's text before it reaches the model."""
    return truncate_text(content, max_chars)
