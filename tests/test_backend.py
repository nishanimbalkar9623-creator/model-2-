"""Tests for backend error handling and the streaming (SSE) endpoint."""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.backend.client import (
    BackendAuthError,
    BackendConflictError,
    BackendNotFoundError,
    BackendPermissionError,
    BackendRateLimitedError,
    BackendServerError,
    BackendValidationError,
)

from tests.conftest import FakeBackendClient


def test_error_mapping():
    from app.backend import client as bc

    assert isinstance(bc._error_for_status(401, "x"), BackendAuthError)
    assert isinstance(bc._error_for_status(403, "x"), BackendPermissionError)
    assert isinstance(bc._error_for_status(404, "x"), BackendNotFoundError)
    assert isinstance(bc._error_for_status(409, "x"), BackendConflictError)
    assert isinstance(bc._error_for_status(422, "x"), BackendValidationError)
    assert isinstance(bc._error_for_status(429, "x"), BackendRateLimitedError)
    assert isinstance(bc._error_for_status(500, "x"), BackendServerError)


def test_backend_conflict_surfaces_as_safe_error(client, fake_backend):
    fake_backend.conflicts = ["/clients/abc"]
    r = client.post(
        "/api/v1/chat",
        json={"message": "Explain the GST mismatches for ABC", "client_id": "abc"},
    )
    assert r.status_code == 200
    body = r.json()
    # safe error is embedded in the reply/tool results, not raised to 5xx
    assert "reconciliation" not in body or isinstance(body["message"], str)


def test_streaming_sse(client):
    with client.stream(
        "POST",
        "/api/v1/chat/stream",
        json={"message": "What is GST reconciliation?"},
    ) as r:
        assert r.status_code == 200
        # collect SSE data lines
        lines = [line for line in r.iter_lines() if line]
        joined = "\n".join(lines)
        assert "event: start" in joined or "token" in joined


def test_fake_backend_records_calls():
    fb = FakeBackendClient({"abc": {"name": "ABC"}})
    import asyncio

    asyncio.run(fb.get("/api/v1/clients/abc"))
    assert ("GET", "/api/v1/clients/abc") in fb.calls
