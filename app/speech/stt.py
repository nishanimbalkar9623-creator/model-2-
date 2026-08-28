"""Speech-to-text abstraction.

The engine receives audio bytes from the frontend and hands them to a
configurable provider. Initial implementation: a mock that returns a placeholder,
plus a hook for OpenAI/Gemini/whisper-local.
"""

from __future__ import annotations

import abc
from dataclasses import dataclass
from typing import Any, Dict, Optional

from app.config import settings


@dataclass
class TranscriptionResult:
    text: str
    language: Optional[str] = None
    confidence: Optional[float] = None
    duration_seconds: Optional[float] = None


class SpeechToTextProvider(abc.ABC):
    name = "base"

    @abc.abstractmethod
    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        language: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> TranscriptionResult:
        ...


class MockSTTProvider(SpeechToTextProvider):
    name = "mock"

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        language: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> TranscriptionResult:
        # deterministic "transcription" from size (never use in prod)
        size_kb = len(audio_bytes) // 1024
        text = f"[mock-transcription: {size_kb} KB audio]"
        return TranscriptionResult(
            text=text, language=language or "en", confidence=0.99
        )


from app.speech.providers.openai import OpenAIWhisperProvider  # noqa: E402


def create_stt_provider() -> SpeechToTextProvider:
    if settings.stt_provider == "mock":
        return MockSTTProvider()
    if settings.stt_provider == "openai":
        return OpenAIWhisperProvider()
    # gemini / whisper-local — same interface; plug in later
    return MockSTTProvider()
