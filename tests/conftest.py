"""Shared pytest fixtures.

Provides a FastAPI TestClient with a MockLLMProvider and a stubbed
BackendClient so tests run purely offline.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# ensure project root importable
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import os

os.environ.setdefault("LLM_PROVIDER", "mock")
os.environ.setdefault("APP_ENV", "testing")


class FakeBackendClient:
    """In-memory stand-in for the real BackendClient.

    Lets tests exercise the engine's HTTP contract without a live backend.
    """

    base_url = "http://fake-backend/"

    def __init__(self, responses=None, conflicts=None):
        self.responses = responses or {}
        self.conflicts = conflicts or []  # list of (method, path)
        self.calls = []

    async def aclose(self):
        pass

    async def _handle(self, method, path):
        self.calls.append((method, path))
        if any(p in path for p in self.conflicts):
            from app.backend.client import BackendConflictError

            raise BackendConflictError("Conflict", 409)
        key = path
        for k, v in self.responses.items():
            if path.startswith(k) or (k in path):
                return {"request": path, "data": v}
        return {"request": path, "data": {"items": []}}

    async def get(self, path, *, params=None, user_id=None, user_role=None, **kw):
        return await self._handle("GET", path)

    async def post(self, path, *, json=None, user_id=None, user_role=None, **kw):
        return await self._handle("POST", path)

    async def patch(self, path, *, json=None, user_id=None, user_role=None, **kw):
        return await self._handle("PATCH", path)

    async def request(self, method, path, **kw):
        return await self._handle(method, path)


@pytest.fixture()
def fake_backend():
    return FakeBackendClient()


@pytest.fixture()
def client(fake_backend):
    from app.agent.orchestrator import AgentOrchestrator
    from app.llm.providers.mock import MockLLMProvider

    orchestrator = AgentOrchestrator(
        llm=MockLLMProvider(),
        backend=fake_backend,
        memory=None,
    )
    from app.main import build_app

    app = build_app()
    app.state.llm = MockLLMProvider()
    app.state.backend = fake_backend
    app.state.orchestrator = orchestrator
    return TestClient(app)
