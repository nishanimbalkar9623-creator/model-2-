"""Tests for the speech-to-text endpoint and STT abstraction."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct execution
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from app.speech.stt import MockSTTProvider


async def test_mock_stt_provider():
    p = MockSTTProvider()
    result = await p.transcribe(b"fake-audio-bytes", language="en")
    assert result.text
    assert result.language == "en"
    assert result.confidence is not None


def test_stt_endpoint(client):
    r = client.post(
        "/api/v1/voice/transcribe",
        files={"file": ("audio.webm", b"some-bytes", "audio/webm")},
        data={"language": "en"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["text"]
    assert body["language"] == "en"


def test_stt_endpoint_empty_rejected(client):
    r = client.post(
        "/api/v1/voice/transcribe",
        files={"file": ("audio.webm", b"", "audio/webm")},
    )
    assert r.status_code == 400


def test_voice_chat_endpoint(client):
    r = client.post(
        "/api/v1/voice/chat",
        files={"file": ("audio.webm", b"sample-speech-bytes", "audio/webm")},
        data={"language": "en"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "transcription" in body
    assert "response" in body
    assert body["response"]["message"]


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__]))
