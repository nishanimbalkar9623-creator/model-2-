"""Google Gemini provider (OpenAI-compatible endpoint is preferred when
available, but this uses the native REST API for completeness)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResult, ToolSpec


class GeminiProvider(LLMProvider):
    name = "gemini"
    base = "https://generativelanguage.googleapis.com/v1beta"

    def __init__(self, api_key: str, model: str):
        self.api_key = api_key
        self.model = model

    @classmethod
    def from_settings(cls) -> "GeminiProvider":
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is not set")
        return cls(settings.gemini_api_key, settings.llm_model or "gemini-1.5-flash")

    def _contents(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        out = []
        for m in messages:
            out.append({"role": m.role, "parts": [{"text": m.content}]})
        return out

    async def _post(self, path: str, body: Dict[str, Any]) -> Dict[str, Any]:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base}/{self.model}:{path}",
                params={"key": self.api_key},
                json=body,
            )
            resp.raise_for_status()
            return resp.json()

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        # NOTE: Gemini returns the answer directly in candidates[].parts.token
        data = await self._post(
            "generateContent",
            {"contents": self._contents(messages), "generationConfig": {"temperature": temperature}},
        )
        text = ""
        cands = data.get("candidates", [])
        if cands:
            parts = cands[0].get("content", {}).get("parts", [])
            text = "".join(p.get("text", "") for p in parts)
        return LLMResult(content=text, model=self.model)

    async def stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        # fall back to one-shot streaming (simple)
        result = await self.generate(messages, tools, temperature, max_tokens, **kwargs)
        for token in result.content.split(" "):
            yield token + " "

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        result = await self.generate([LLMMessage("user", prompt)], temperature=0.0, **kwargs)
        return result.content
