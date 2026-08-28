"""Mock LLM provider for development & tests.

Returns deterministic, helpful responses derived from the last user message
and (optionally) a configured intent classifier. Used when ``LLM_PROVIDER=mock``
or when a real provider is unavailable.
"""

from __future__ import annotations

import random
import string
from typing import Any, AsyncIterator, Dict, List, Optional

from app.llm.base import LLMMessage, LLMProvider, LLMResult, ToolSpec


def _rand_id() -> str:
    return "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


class MockLLMProvider(LLMProvider):
    name = "mock"

    def __init__(self) -> None:
        self.intent = "general"

    async def classify_intent(self, message: str) -> str:
        """Simple keyword-free heuristic to choose an intent for mock responses."""
        text = message.lower()
        if any(w in text for w in ["schedule", "create task", "create meeting", "generate report", "export", "process", "reconcile"]):
            return "action"
        if any(w in text for w in ["mismatch", "exception", "explain the gst", "analysis", "reconciliation"]):
            return "data_analysis"
        if "report" in text:
            return "report"
        if any(w in text for w in ["for abc", "client abc", "pending for", "status of"]):
            return "client_specific"
        return "general"

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        last_user = ""
        for m in reversed(messages):
            if m.role == "user":
                last_user = m.content
                break

        self.intent = await self.classify_intent(last_user)

        content = (
            f"[mock] I analyzed your request: '{last_user[:120]}'. "
            f"Intent classified as '{self.intent}'. For a production deployment, "
            f"configure LLM_PROVIDER=[openai|gemini|anthropic|ollama] and set the "
            f"appropriate model keys."
        )

        tool_calls: List[Dict[str, Any]] = []
        if self.intent == "action":
            first = tools[0] if tools else None
            if first:
                tool_calls.append({"name": first.name, "arguments": {}})

        return LLMResult(content=content, tool_calls=tool_calls, model="mock")

    async def stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        result = await self.generate(messages, tools, temperature, max_tokens, **kwargs)
        # yield a few tokens to simulate progressive output
        tokens = result.content.split(" ")
        for idx, tok in enumerate(tokens):
            yield tok + (" " if idx < len(tokens) - 1 else "")
            # make the coroutine async-friendly
            if idx == 999999:
                break

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        intent = await self.classify_intent(prompt)
        return f'{{"intent": "{intent}"}}'
