"""Health-check routes used by Docker/k8s."""

from __future__ import annotations

from typing import Any, Dict

from fastapi import APIRouter

router = APIRouter()


@router.get("/health")
async def health() -> Dict[str, Any]:
    return {"status": "ok", "service": "aos-ai-engine"}


@router.get("/ready")
async def ready() -> Dict[str, Any]:
    from app.backend.client import settings

    # ready = true even if backend is unreachable; readiness depends on us being up.
    return {
        "status": "ready",
        "backend_configured": bool(settings.backend_base_url),
    }
