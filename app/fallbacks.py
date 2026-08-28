"""Fallback handlers for graceful degradation when services are unavailable."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from app.agent.workflows import WorkflowName
from app.llm.base import LLMMessage, LLMProvider, LLMResult
from app.llm.providers.mock import MockLLMProvider
from app.rag.knowledge import CAKnowledgeBase
from app.rag.document_search import ClientDocumentStore
from app.speech.stt import SpeechToTextProvider, TranscriptionResult, MockSTTProvider

logger = logging.getLogger("aos.fallbacks")


class FallbackLLMProvider(LLMProvider):
    """Fallback LLM provider that uses MockLLMProvider."""
    
    name = "fallback"
    
    def __init__(self, original_provider_name: str):
        self.original_provider_name = original_provider_name
        self._mock = MockLLMProvider()
        logger.warning(f"LLM provider '{original_provider_name}' failed, falling back to mock")
    
    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Any]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        return await self._mock.generate(messages, tools, temperature, max_tokens, **kwargs)
    
    async def stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[Any]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ):
        async for token in self._mock.stream(messages, tools, temperature, max_tokens, **kwargs):
            yield token
    
    async def complete(self, prompt: str, **kwargs: Any) -> str:
        return await self._mock.complete(prompt, **kwargs)


class FallbackSTTProvider(SpeechToTextProvider):
    """Fallback STT provider that uses MockSTTProvider."""
    
    name = "fallback-stt"
    
    def __init__(self, original_provider_name: str):
        self.original_provider_name = original_provider_name
        self._mock = MockSTTProvider()
        logger.warning(f"STT provider '{original_provider_name}' failed, falling back to mock")
    
    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        language: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> TranscriptionResult:
        return await self._mock.transcribe(audio_bytes, language=language, mime_type=mime_type)


def get_fallback_llm_provider(provider_name: str) -> FallbackLLMProvider:
    """Create a fallback LLM provider."""
    return FallbackLLMProvider(provider_name)


def get_fallback_stt_provider(provider_name: str) -> FallbackSTTProvider:
    """Create a fallback STT provider."""
    return FallbackSTTProvider(provider_name)


class GracefulDegradation:
    """Manages graceful degradation for the AI Engine."""
    
    def __init__(self):
        self._llm_failed = False
        self._backend_failed = False
        self._stt_failed = False
        self._rag_failed = False
    
    def mark_llm_failed(self, provider_name: str) -> FallbackLLMProvider:
        """Mark LLM as failed and return fallback."""
        if not self._llm_failed:
            self._llm_failed = True
            logger.error(f"LLM provider '{provider_name}' marked as failed")
        return get_fallback_llm_provider(provider_name)
    
    def mark_backend_failed(self) -> None:
        """Mark backend as failed."""
        if not self._backend_failed:
            self._backend_failed = True
            logger.error("Backend marked as failed")
    
    def mark_stt_failed(self, provider_name: str) -> FallbackSTTProvider:
        """Mark STT as failed and return fallback."""
        if not self._stt_failed:
            self._stt_failed = True
            logger.error(f"STT provider '{provider_name}' marked as failed")
        return get_fallback_stt_provider(provider_name)
    
    def mark_rag_failed(self) -> None:
        """Mark RAG as failed."""
        if not self._rag_failed:
            self._rag_failed = True
            logger.error("RAG marked as failed")
    
    def is_degraded(self) -> bool:
        """Check if any service is in fallback mode."""
        return any([self._llm_failed, self._backend_failed, self._stt_failed, self._rag_failed])
    
    def get_status(self) -> Dict[str, bool]:
        """Get degradation status."""
        return {
            "llm_failed": self._llm_failed,
            "backend_failed": self._backend_failed,
            "stt_failed": self._stt_failed,
            "rag_failed": self._rag_failed,
        }
    
    def get_degradation_message(self) -> str:
        """Get user-facing degradation message."""
        parts = []
        if self._llm_failed:
            parts.append("AI responses are in limited mode")
        if self._backend_failed:
            parts.append("Client data unavailable")
        if self._stt_failed:
            parts.append("Voice input unavailable")
        if self._rag_failed:
            parts.append("Knowledge search unavailable")
        return "; ".join(parts) if parts else "All systems operational"


# Global instance
_degradation = GracefulDegradation()


def get_degradation_manager() -> GracefulDegradation:
    return _degradation


async def safe_llm_generate(
    provider: LLMProvider,
    messages: List[LLMMessage],
    tools: Optional[List[Any]] = None,
    **kwargs: Any,
) -> LLMResult:
    """Safely generate with fallback on failure."""
    try:
        return await provider.generate(messages, tools, **kwargs)
    except Exception as e:
        logger.error(f"LLM generation failed: {e}")
        fallback = _degradation.mark_llm_failed(getattr(provider, "name", "unknown"))
        return await fallback.generate(messages, tools, **kwargs)


async def safe_stt_transcribe(
    provider: SpeechToTextProvider,
    audio_bytes: bytes,
    **kwargs: Any,
) -> TranscriptionResult:
    """Safely transcribe with fallback on failure."""
    try:
        return await provider.transcribe(audio_bytes, **kwargs)
    except Exception as e:
        logger.error(f"STT transcription failed: {e}")
        fallback = _degradation.mark_stt_failed(getattr(provider, "name", "unknown"))
        return await fallback.transcribe(audio_bytes, **kwargs)


def safe_rag_query(
    query: str,
    client_id: Optional[str] = None,
    top_k: int = 3,
) -> List[Any]:
    """Safely query RAG with fallback."""
    try:
        if client_id:
            store = ClientDocumentStore()
            return store.search(query, client_id=client_id, top_k=top_k)
        else:
            kb = CAKnowledgeBase()
            return kb.query(query, top_k=top_k)
    except Exception as e:
        logger.error(f"RAG query failed: {e}")
        _degradation.mark_rag_failed()
        return []


def safe_backend_call(
    backend,
    method: str,
    path: str,
    **kwargs: Any,
) -> Any:
    """Safely call backend with error handling."""
    try:
        return getattr(backend, method)(path, **kwargs)
    except Exception as e:
        logger.error(f"Backend call failed: {e}")
        _degradation.mark_backend_failed()
        raise