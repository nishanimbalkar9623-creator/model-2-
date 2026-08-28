"""OpenAI-compatible provider (also covers many hosted APIs)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResult, ToolSpec


class OpenAICompatProvider(LLMProvider):
    name = "openai"

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.openai.com/v1"

    @classmethod
    def from_settings(cls) -> "OpenAICompatProvider":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY is not set")
        model = settings.llm_model or "gpt-4o-mini"
        return cls(
            settings.openai_api_key,
            model,
            settings.openai_base_url,
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

    def _to_openai(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        return [{"role": m.role, "content": m.content} for m in messages]

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai(messages),
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = [t.to_provider(self) for t in tools]
            body["tool_choice"] = "auto"

        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            )
            resp.raise_for_status()
            data = resp.json()

        choice = data["choices"][0]["message"]
        tool_calls = []
        for tc in choice.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            tool_calls.append(
                {
                    "name": fn.get("name"),
                    "arguments": _safe_json(fn.get("arguments", "{}")),
                }
            )
        usage = data.get("usage", {})
        return LLMResult(
            content=choice.get("content") or "",
            tool_calls=tool_calls,
            model=data.get("model"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    async def stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        body: Dict[str, Any] = {
            "model": self.model,
            "messages": self._to_openai(messages),
            "temperature": temperature,
            "stream": True,
        }
        if tools:
            body["tools"] = [t.to_provider(self) for t in tools]
        async with httpx.AsyncClient(timeout=60.0) as client:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=body,
            ) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    if not line or not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        import json

                        chunk = json.loads(payload)
                        delta = chunk["choices"][0]["delta"]
                        content = delta.get("content") or ""
                        if content:
                            yield content
                    except Exception:
                        continue

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        result = await self.generate(
            [LLMMessage("user", prompt)],
            temperature=0.0,
            **kwargs,
        )
        return result.content


def _safe_json(text: str) -> Dict[str, Any]:
    import json

    try:
        return json.loads(text)
    except Exception:
        return {}
