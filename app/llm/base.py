"""LLM provider abstraction.

The engine depends only on this interface, never on a specific vendor.
Implementations live under ``app/llm/providers`` and are selected by
``LLM_PROVIDER`` in configuration.
"""

from __future__ import annotations

import abc
from typing import Any, AsyncIterator, Dict, List, Optional


class LLMMessage:
    """A single chat turn in the provider-agnostic format."""

    def __init__(self, role: str, content: str):
        self.role = role  # system | user | assistant | tool
        self.content = content


class ToolSpec:
    """Provider-agnostic function/tool specification."""

    def __init__(
        self,
        name: str,
        description: str,
        parameters: Dict[str, Any],
    ):
        self.name = name
        self.description = description
        self.parameters = parameters

    def to_provider(self, provider: "LLMProvider") -> Any:
        return provider.build_tool_spec(self)


class LLMResult:
    def __init__(
        self,
        content: str,
        tool_calls: Optional[List[Dict[str, Any]]] = None,
        model: Optional[str] = None,
        input_tokens: Optional[int] = None,
        output_tokens: Optional[int] = None,
    ):
        self.content = content
        # list of {"name": str, "arguments": dict}
        self.tool_calls = tool_calls or []
        self.model = model
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class LLMProvider(abc.ABC):
    """Base class for all LLM providers."""

    name: str = "base"

    @abc.abstractmethod
    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        """Return a single (possibly tool-calling) completion."""

    def stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        """Optionally override for token streaming. Defaults to one-shot."""
        raise NotImplementedError

    @abc.abstractmethod
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        """Simple single-prompt completion helper (for classification etc.)."""

    def build_tool_spec(self, spec: ToolSpec) -> Any:
        """Convert an engine ToolSpec into the provider-native form."""
        return {
            "type": "function",
            "function": {
                "name": spec.name,
                "description": spec.description,
                "parameters": spec.parameters,
            },
        }

    def health(self) -> Dict[str, Any]:
        return {"provider": self.name, "ok": True}
