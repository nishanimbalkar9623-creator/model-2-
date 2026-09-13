"""Tests for health/readiness and basic app wiring."""

from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path for direct execution
_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_ready(client):
    r = client.get("/ready")
    assert r.status_code == 200
    assert r.json()["status"] == "ready"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert "service" in r.json()


def test_unknown_provider_raises():
    from app.llm.factory import create_provider

    try:
        create_provider("nope")
        raised = False
    except ValueError:
        raised = True
    assert raised


if __name__ == "__main__":
    import pytest

    sys.exit(pytest.main([__file__]))
