"""Speech-to-text and voice chat endpoints.

The frontend POSTs raw audio bytes; the engine forwards to the configured
STT provider and returns text.
Voice chat transcribes audio and passes it through the same agent pipeline.
"""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile

from app.api.routes_chat import _get_orchestrator
from app.speech.stt import create_stt_provider

router = APIRouter(prefix="/api/v1")

MAX_AUDIO_BYTES = 10 * 1024 * 1024  # 10 MB


@router.post("/voice/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    language: str = Form(default=""),
) -> Dict[str, Any]:
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large.")

    provider = create_stt_provider()
    result = await provider.transcribe(
        audio_bytes,
        language=language or None,
        mime_type=file.content_type,
    )
    return {
        "text": result.text,
        "language": result.language,
        "confidence": result.confidence,
        "provider": provider.name,
        "duration_seconds": result.duration_seconds,
    }


@router.post("/voice/chat")
async def voice_chat(
    request: Request,
    file: UploadFile = File(...),
    language: str = Form(default=""),
    client_id: str = Form(default=""),
    conversation_id: str = Form(default=""),
    user_id: str = Form(default=""),
    user_role: str = Form(default=""),
) -> Dict[str, Any]:
    """Transcribe audio and run through the agent pipeline.
    
    Returns the same response structure as /api/v1/chat.
    """
    audio_bytes = await file.read()
    if not audio_bytes:
        raise HTTPException(status_code=400, detail="Empty audio file.")
    if len(audio_bytes) > MAX_AUDIO_BYTES:
        raise HTTPException(status_code=413, detail="Audio file too large.")

    # Transcribe
    provider = create_stt_provider()
    result = await provider.transcribe(
        audio_bytes,
        language=language or None,
        mime_type=file.content_type,
    )

    if not result.text:
        raise HTTPException(status_code=400, detail="Could not transcribe audio.")

    # If in mock mode, use a standard query for agent execution
    agent_message = result.text
    if agent_message.startswith("[mock-transcription"):
        agent_message = "What is the status of reconciliation?"

    # Run through agent
    orch = _get_orchestrator(request)
    
    response = await orch.run(
        message=agent_message,
        client_id=client_id or None,
        conversation_id=conversation_id or None,
        user_id=user_id or None,
        user_role=user_role or None,
    )
    
    return {
        "transcription": {
            "text": result.text,
            "language": result.language,
            "confidence": result.confidence,
        },
        "response": response.model_dump(),
    }
