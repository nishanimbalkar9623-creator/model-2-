"""Tests for health/readiness and basic app wiring."""

from __future__ import annotations


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
