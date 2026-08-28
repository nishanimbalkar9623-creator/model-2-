"""Tests for the /api/v1/chat endpoint and intent routing."""

from __future__ import annotations

from app.schemas.agent import IntentType


def test_chat_general(client):
    r = client.post("/api/v1/chat", json={"message": "What is GST reconciliation?"})
    assert r.status_code == 200
    body = r.json()
    assert body["conversation_id"]
    assert body["message"]
    assert isinstance(body["tool_calls"], list)


def test_chat_returns_conversation_id(client):
    r1 = client.post("/api/v1/chat", json={"message": "Hello"})
    cid1 = r1.json()["conversation_id"]
    r2 = client.post(
        "/api/v1/chat", json={"message": "Hello again", "conversation_id": cid1}
    )
    assert r2.json()["conversation_id"] == cid1


def test_chat_empty_message_rejected(client):
    r = client.post("/api/v1/chat", json={"message": ""})
    assert r.status_code == 422


def test_intent_classifier_general():
    from app.agent.planner import classify_intent_text

    assert classify_intent_text("What is GST reconciliation?") == IntentType.GENERAL


def test_intent_classifier_client():
    from app.agent.planner import classify_intent_text

    assert classify_intent_text("What is pending for ABC?") == IntentType.CLIENT_SPECIFIC


def test_intent_classifier_action():
    from app.agent.planner import classify_intent_text

    assert classify_intent_text("Schedule a meeting tomorrow at 3 PM") == IntentType.ACTION


def test_intent_classifier_analysis():
    from app.agent.planner import classify_intent_text

    assert classify_intent_text("Explain the GST mismatches") == IntentType.DATA_ANALYSIS
