"""Local Ollama provider (OpenAI-compatible REST API)."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResult, ToolSpec


class OllamaProvider(LLMProvider):
    name = "ollama"

    def __init__(self, base_url: str, model: str):
        self.base_url = base_url.rstrip("/")
        self.model = model

    @classmethod
    def from_settings(cls) -> "OllamaProvider":
        return cls(
            settings.ollama_base_url,
            settings.llm_model or "llama3.2",
        )

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
            "stream": False,
            "options": {"temperature": temperature},
        }
        if tools:
            body["tools"] = [t.to_provider(self) for t in tools]
        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(f"{self.base_url}/api/chat", json=body)
            resp.raise_for_status()
            data = resp.json()
        content = data.get("message", {}).get("content", "")
        tool_calls = []
        for tc in data.get("message", {}).get("tool_calls", []) or []:
            tool_calls.append({"name": tc.get("function", {}).get("name"), "arguments": tc.get("function", {}).get("arguments", {})})
        return LLMResult(content=content, tool_calls=tool_calls, model=data.get("model"))

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
            "stream": True,
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream("POST", f"{self.base_url}/api/chat", json=body) as resp:
                resp.raise_for_status()
                async for line in resp.aiter_lines():
                    import json

                    try:
                        data = json.loads(line)
                    except Exception:
                        continue
                    if data.get("done"):
                        break
                    chunk = data.get("message", {}).get("content", "")
                    if chunk:
                        yield chunk

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return (await self.generate([LLMMessage("user", prompt)], temperature=0.0, **kwargs)).content

    def health(self) -> Dict[str, Any]:
        return {"provider": self.name, "ok": True, "base_url": self.base_url}
