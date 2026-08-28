"""Anthropic-compatible provider (Claude). Uses httpx directly so it also
works with compatible proxies by overriding ANTHROPIC_BASE_URL."""

from __future__ import annotations

from typing import Any, AsyncIterator, Dict, List, Optional

import httpx

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResult, ToolSpec


class AnthropicProvider(LLMProvider):
    name = "anthropic"

    def __init__(self, api_key: str, model: str, base_url: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.base_url = base_url or "https://api.anthropic.com/v1"

    @classmethod
    def from_settings(cls) -> "AnthropicProvider":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY is not set")
        return cls(
            settings.anthropic_api_key,
            settings.llm_model or "claude-3-5-haiku-latest",
            settings.anthropic_base_url,
        )

    def _headers(self) -> Dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

    def _to_anthropic(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        out = []
        for m in messages:
            if m.role == "system":
                continue
            out.append({"role": "assistant" if m.role == "assistant" else "user", "content": m.content})
        return out

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        system = "\n".join(m.content for m in messages if m.role == "system")
        body: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or 1024,
            "messages": self._to_anthropic(messages),
            "temperature": temperature,
        }
        if system:
            body["system"] = system
        if tools:
            body["tools"] = [
                {
                    "name": t.name,
                    "description": t.description,
                    "input_schema": t.parameters,
                }
                for t in tools
            ]
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(
                f"{self.base_url}/messages", headers=self._headers(), json=body
            )
            resp.raise_for_status()
            data = resp.json()
        content, tool_calls = [], []
        for block in data.get("content", []):
            if block.get("type") == "text":
                content.append(block.get("text", ""))
            elif block.get("type") == "tool_use":
                tool_calls.append({"name": block.get("name"), "arguments": block.get("input", {})})
        return LLMResult(
            content="".join(content),
            tool_calls=tool_calls,
            model=data.get("model"),
        )

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return (await self.generate([LLMMessage("user", prompt)], temperature=0.0, **kwargs)).content
