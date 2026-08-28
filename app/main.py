"""AOS AI Engine — FastAPI application.

Single service. All business logic lives in app/*.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, Dict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes_health import router as health_router
from app.api.routes_chat import router as chat_router
from app.api.routes_voice import router as voice_router
from app.config import settings
from app.observability.middleware import RequestLoggingMiddleware


def build_app() -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI):
        from app.agent.orchestrator import AgentOrchestrator
        from app.backend.client import BackendClient
        from app.llm.factory import create_provider
        from app.memory.conversation import ConversationMemory

        llm = create_provider()
        backend = BackendClient()

        orch = AgentOrchestrator(
            llm=llm,
            backend=backend,
            memory=ConversationMemory(),
        )

        app.state.llm = llm
        app.state.backend = backend
        app.state.orchestrator = orch
        yield
        await backend.aclose()
        closer = getattr(llm, "aclose", None)
        if closer:
            await closer()

    app = FastAPI(
        title="AOS AI Engine",
        version="0.1.0",
        description="AI operating platform for Chartered Accountants.",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # tighten in production
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(health_router)
    app.include_router(chat_router)
    app.include_router(voice_router)

    @app.get("/")
    async def root() -> Dict[str, Any]:
        return {
            "service": "AOS AI Engine",
            "provider": settings.llm_provider,
            "docs": "/docs",
        }

    return app


app = build_app()
