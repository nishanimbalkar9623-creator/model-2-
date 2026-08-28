"""Factory that selects the LLM provider from configuration.

Keeps the rest of the engine provider-independent.
"""

from __future__ import annotations

from typing import Dict, Optional, Type

from app.config import get_settings
from app.llm.base import LLMProvider

_REGISTRY: Dict[str, Type[LLMProvider]] = {}


def register(name: str, cls: Type[LLMProvider]) -> None:
    _REGISTRY[name] = cls


def create_provider(name: Optional[str] = None) -> LLMProvider:
    from app.config import settings

    provider_name = name or settings.llm_provider

    if provider_name == "mock":
        from app.llm.providers.mock import MockLLMProvider

        return MockLLMProvider()

    if provider_name == "openai":
        from app.llm.providers.openai import OpenAICompatProvider

        return OpenAICompatProvider.from_settings()

    if provider_name == "gemini":
        from app.llm.providers.gemini import GeminiProvider

        return GeminiProvider.from_settings()

    if provider_name == "anthropic":
        from app.llm.providers.anthropic import AnthropicProvider

        return AnthropicProvider.from_settings()

    if provider_name == "ollama":
        from app.llm.providers.ollama import OllamaProvider

        return OllamaProvider.from_settings()

    raise ValueError(f"Unknown LLM provider: {provider_name}")
