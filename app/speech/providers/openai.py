"""OpenAI Whisper provider (STT)."""

from __future__ import annotations

from typing import Optional

import httpx

from app.config import settings
from app.speech.stt import SpeechToTextProvider, TranscriptionResult


class OpenAIWhisperProvider(SpeechToTextProvider):
    name = "openai-whisper"

    def __init__(self, api_key: Optional[str] = None, model: str = "whisper-1"):
        self.api_key = api_key or settings.openai_api_key or ""
        self.model = settings.stt_model or model

    async def transcribe(
        self,
        audio_bytes: bytes,
        *,
        language: Optional[str] = None,
        mime_type: Optional[str] = None,
    ) -> TranscriptionResult:
        if not self.api_key:
            raise ValueError("OpenAI API key not set for whisper STT")

        # OpenAI expects multipart
        files = {"file": ("audio", audio_bytes, mime_type or "audio/webm")}
        data = {"model": self.model}
        if language:
            data["language"] = language

        async with httpx.AsyncClient(timeout=120.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/audio/transcriptions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                files=files,
                data=data,
            )
            resp.raise_for_status()
            payload = resp.json()
        return TranscriptionResult(
            text=payload.get("text", ""),
            language=language,
            confidence=payload.get("confidence"),
        )
