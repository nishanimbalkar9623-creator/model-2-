"""Tests for conversation memory."""

from __future__ import annotations

from app.memory.conversation import ConversationMemory


def test_get_or_create_same_id():
    m = ConversationMemory()
    c = m.get_or_create("c1", user_id="u1")
    c2 = m.get_or_create("c1", user_id="u1")
    assert c is c2


def test_create_new_when_missing():
    m = ConversationMemory()
    c1 = m.get_or_create("c1", None)
    c2 = m.get_or_create("c2", None)
    assert c1.conversation_id != c2.conversation_id


def test_add_turn_preserved():
    m = ConversationMemory()
    m.get_or_create("c1", None)
    m.add_turn("c1", {"role": "user", "content": "hi"})
    conv = m.get("c1")
    assert len(conv.messages) == 1
    assert conv.messages[0]["content"] == "hi"


def test_ttl_expiry():
    m = ConversationMemory(ttl_seconds=-1)  # instantly expired
    m.get_or_create("cx", None)
    assert m.get("cx") is None


def test_pending_action():
    m = ConversationMemory()
    m.get_or_create("c1", None)
    m.set_pending_action("c1", {"tool": "a", "args": {}})
    assert m.get_pending_action("c1")["tool"] == "a"
    m.clear_pending_action("c1")
    assert m.get_pending_action("c1") is None
