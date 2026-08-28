"""OpenRouter provider + key pool tests (offline, no real API calls)."""

from __future__ import annotations

import asyncio
import logging
import os
from typing import Any, Dict, List, Optional

import httpx
import pytest

# Ensure no accidental real network / key usage during these tests.
os.environ.setdefault("LLM_PROVIDER", "mock")

from app.llm.base import LLMMessage, ToolSpec
from app.llm.errors import (
    LLMAuthenticationError,
    LLMInvalidRequestError,
    LLMRateLimitError,
    LLMUnavailableError,
)
from app.llm.key_pool import OpenRouterKeyPool, mask_key
from app.llm.providers.openrouter import OpenRouterProvider

TOOL_SPEC = ToolSpec(
    name="get_pending_work",
    description="Get pending work for a client",
    parameters={
        "type": "object",
        "properties": {"client_id": {"type": "string"}},
        "required": ["client_id"],
    },
)


class FakeTransport(httpx.AsyncBaseTransport):
    """Reusable in-memory transport returning scripted responses per key."""

    def __init__(self, handler):
        self.handler = handler  # async fn(request) -> httpx.Response
        self.requests = []

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        return await self.handler(request)


def make_provider(keys, *, responses=None, **kw) -> OpenRouterProvider:
    states = {"responses": responses or [], "idx": 0}
    handler_state = {"count": 0}

    async def handler(request: httpx.Request) -> httpx.Response:
        key = request.headers.get("Authorization", "")
        status, body = states["responses"][
            handler_state["count"] % len(states["responses"])
        ] if states["responses"] else (200, _ok_body())
        handler_state["count"] += 1
        headers = {}
        if isinstance(status, tuple):
            status, headers = status
        return httpx.Response(status, json=body, headers=headers)

    client = httpx.AsyncClient(transport=FakeTransport(handler))
    provider = OpenRouterProvider(
        key_pool=OpenRouterKeyPool(keys=keys, cooldown_seconds=0.0),
        base_url="https://or.test/api/v1",
        **kw,
    )
    provider._client = client
    return provider


def _ok_body(content: str = "hi") -> Dict[str, Any]:
    return {
        "id": "cmpl-test",
        "model": "openai/gpt-4o-mini",
        "choices": [{"message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5},
    }


def _tool_body(name: str = "get_pending_work") -> Dict[str, Any]:
    return {
        "id": "cmpl-tool",
        "model": "openai/gpt-4o-mini",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [
                        {
                            "function": {
                                "name": name,
                                "arguments": '{"client_id":"ABC"}',
                            }
                        }
                    ],
                }
            }
        ],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1},
    }


# ---------------------------------------------------------------------------
# 1. Provider creation / factory selection
# ---------------------------------------------------------------------------


def test_provider_creation_with_keys():
    pool = OpenRouterKeyPool(keys=["sk-or-aaa", "sk-or-bbb"])
    provider = OpenRouterProvider(key_pool=pool)
    assert provider.name == "openrouter"
    assert provider.key_pool.total == 2


def test_factory_selects_openrouter(monkeypatch):
    from app.config import settings
    from app.llm import factory

    monkeypatch.setattr(settings, "llm_provider", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY_1", "sk-or-testkey")
    provider = factory.create_provider("openrouter")
    assert isinstance(provider, OpenRouterProvider)
    monkeypatch.delenv("OPENROUTER_API_KEY_1", raising=False)


def test_no_key_configured_raises():
    pool = OpenRouterKeyPool(keys=[])
    with pytest.raises(LLMUnavailableError):
        OpenRouterProvider(key_pool=pool)


def test_paste_placeholder_keys_ignored():
    pool = OpenRouterKeyPool(keys=["PASTE_OPENROUTER_KEY_HERE", "", "sk-or-real"])
    assert pool.total == 1


# ---------------------------------------------------------------------------
# 3/4. One vs multiple keys
# ---------------------------------------------------------------------------


def test_single_key_healthy():
    pool = OpenRouterKeyPool(keys=["sk-or-one"])
    assert pool.total == 1
    assert pool.healthy == 1


def test_multiple_keys_loaded():
    pool = OpenRouterKeyPool(keys=["sk-or-1", "sk-or-2", "sk-or-3"])
    assert pool.total == 3
    assert pool.healthy == 3


# ---------------------------------------------------------------------------
# 5. Round-robin rotation
# ---------------------------------------------------------------------------


def test_round_robin_rotation():
    pool = OpenRouterKeyPool(keys=["sk-or-1", "sk-or-2", "sk-or-3"])
    idxes = [asyncio.run(pool.next_healthy_index()) for _ in range(5)]
    assert idxes == [1, 2, 3, 1, 2]


# ---------------------------------------------------------------------------
# 6. 429 -> next key (retry on another key)
# ---------------------------------------------------------------------------


def test_429_retries_on_next_key():
    provider = make_provider(
        ["sk-or-1", "sk-or-2"],
        responses=[(429, {"error": {"message": "slow down"}}), (200, _ok_body())],
    )
    result = asyncio.run(
        provider.generate([LLMMessage("user", "hi")], tools=[TOOL_SPEC])
    )
    assert result.content == "hi"
    keys_used = _auth_keys(provider)
    assert keys_used[0] != keys_used[1]  # rotated to another key


# ---------------------------------------------------------------------------
# 7/8. 401 / 403 -> key disabled
# ---------------------------------------------------------------------------


def test_401_disables_key_and_uses_other():
    provider = make_provider(
        ["sk-or-1", "sk-or-2"],
        responses=[(401, {"error": {"message": "invalid key"}}), (200, _ok_body())],
    )
    result = asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    assert result.content == "hi"
    # key 1 disabled (401 long cooldown), key 2 healthy
    assert provider.key_pool.healthy == 1


def test_403_disables_key():
    pool = OpenRouterKeyPool(keys=["sk-or-1", "sk-or-2"], cooldown_seconds=0.0)
    asyncio.run(pool.acquire_healthy())
    pool.mark_failure(1, "403")
    available = [asyncio.run(pool.next_healthy_index()) for _ in range(4)]
    assert 1 not in available
    assert set(available) == {2} or any(a == 2 for a in available)


# ---------------------------------------------------------------------------
# 9. 500 -> retry
# ---------------------------------------------------------------------------


def test_500_retries():
    provider = make_provider(
        ["sk-or-1", "sk-or-2", "sk-or-3"],
        responses=[(500, {"error": {"message": "boom"}}), (503, {}), (200, _ok_body())],
        max_retries=3,
    )
    result = asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    assert result.content == "hi"


# ---------------------------------------------------------------------------
# 10. Timeout -> retry
# ---------------------------------------------------------------------------


def test_timeout_retries(monkeypatch):
    provider = make_provider(
        ["sk-or-1", "sk-or-2"],
        responses=[(200, _ok_body()), (200, _ok_body())],
        max_retries=2,
    )
    called = {"n": 0}

    class FakeClient:
        is_closed = False

        async def post(self, *a, **k):
            called["n"] += 1
            if called["n"] == 1:
                raise httpx.ReadTimeout("read timed out")
            return httpx.Response(200, json=_ok_body())

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    provider._client = FakeClient()  # type: ignore[assignment]
    result = asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    assert result.content == "hi"
    assert called["n"] == 2


# ---------------------------------------------------------------------------
# 11. 400 -> no blind retry
# ---------------------------------------------------------------------------


def test_400_no_blind_retry():
    provider = make_provider(
        ["sk-or-1", "sk-or-2"],
        responses=[(400, {"error": {"message": "bad model"}})],
        max_retries=5,
    )
    with pytest.raises(LLMInvalidRequestError):
        asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    # should not have rotated / exhausted retries wastefully
    assert provider.key_pool.healthy == 2  # 400 does not disable keys


# ---------------------------------------------------------------------------
# 12. Max retry limit
# ---------------------------------------------------------------------------


def test_max_retry_limit_respected():
    provider = make_provider(
        ["sk-or-1", "sk-or-2", "sk-or-3"],
        responses=[(429, {})],
        max_retries=2,
    )
    with pytest.raises(LLMRateLimitError):
        asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    # attempts capped at min(max_retries, keys)
    assert len(provider._client._transport.requests) <= 2  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# 13. Cooldown recovery
# ---------------------------------------------------------------------------


def test_cooldown_recovery():
    pool = OpenRouterKeyPool(keys=["sk-or-1"], cooldown_seconds=0.05)
    assert asyncio.run(pool.next_healthy_index()) == 1
    pool.mark_failure(1, "429")
    assert pool.healthy == 0
    assert asyncio.run(pool.acquire_healthy()) is None
    asyncio.run(asyncio.sleep(0.15))  # wait past cooldown
    assert pool.healthy == 1
    assert asyncio.run(pool.next_healthy_index()) == 1


# ---------------------------------------------------------------------------
# 14. Concurrent requests — no single-key stampede
# ---------------------------------------------------------------------------


def test_concurrent_requests_use_different_keys():
    pool = OpenRouterKeyPool(keys=["sk-or-1", "sk-or-2", "sk-or-3"])

    async def worker():
        return await pool.next_healthy_index()

    async def run():
        return await asyncio.gather(*[worker() for _ in range(9)])

    results = asyncio.run(run())
    # With healthy keys, round-robin must spread across all three.
    assert set(results) == {1, 2, 3}
    counts = [results.count(i) for i in (1, 2, 3)]
    assert counts == [3, 3, 3]


# ---------------------------------------------------------------------------
# 15/16. Key masking in logs & no key in exceptions
# ---------------------------------------------------------------------------


def test_key_masking(caplog):
    key = "sk-or-v1-supersecret123456"
    assert mask_key(key) != key
    assert key not in mask_key(key)
    assert "****" in mask_key(key)


def test_no_key_in_exceptions(caplog):
    provider = make_provider(
        ["sk-or-v1-verysecretvalue"],
        responses=[(429, {"error": {"message": "rate"}})],
    )
    with pytest.raises(LLMRateLimitError) as ei:
        asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    text = str(ei.value)
    assert "verysecretvalue" not in text
    assert "sk-or" not in text


def test_no_raw_key_in_logs(caplog):
    key = "sk-or-v1-ultrasecret999"
    provider = make_provider(
        [key, "sk-or-other", "sk-or-third"],
        responses=[(429, {}), (500, {}), (200, _ok_body())],
        max_retries=3,
    )
    with caplog.at_level(logging.INFO):
        asyncio.run(provider.generate([LLMMessage("user", "hi")]))
    combined = caplog.text
    assert "ultrasecret999" not in combined
    assert key not in combined


# ---------------------------------------------------------------------------
# 17. Mock provider unaffected
# ---------------------------------------------------------------------------


def test_mock_provider_unaffected():
    from app.llm.providers.mock import MockLLMProvider

    provider = MockLLMProvider()
    result = asyncio.run(provider.generate([LLMMessage("user", "hello")]))
    assert result.content.startswith("[mock]")
    assert provider.name == "mock"


# ---------------------------------------------------------------------------
# 18. Tool calling schema compatibility
# ---------------------------------------------------------------------------


def test_tool_schema_translation():
    provider = make_provider(["sk-or-1"])
    body = provider._build_body(
        [LLMMessage("user", "hi")],
        [TOOL_SPEC],
        temperature=0.2,
        max_tokens=None,
        model="m",
    )
    assert body["tools"][0]["type"] == "function"
    assert body["tools"][0]["function"]["name"] == "get_pending_work"
    assert body["tool_choice"] == "auto"


def test_tool_call_parsing():
    provider = make_provider(["sk-or-1"], responses=[(200, _tool_body())])
    result = asyncio.run(
        provider.generate([LLMMessage("user", "hi")], tools=[TOOL_SPEC])
    )
    assert result.tool_calls[0]["name"] == "get_pending_work"
    assert result.tool_calls[0]["arguments"] == {"client_id": "ABC"}


# ---------------------------------------------------------------------------
# 19. Streaming
# ---------------------------------------------------------------------------


def test_streaming_yields_tokens():
    async def handler(request):
        # trivial SSE stream
        lines = "data: {\"choices\":[{\"delta\":{\"content\":\"Hel\"}}]}\n" \
                "data: {\"choices\":[{\"delta\":{\"content\":\"lo\"}}]}\n" \
                "data: [DONE]\n\n"
        return httpx.Response(200, content=lines.encode())

    provider = make_provider(["sk-or-1"])
    provider._client = httpx.AsyncClient(transport=FakeTransport(handler))

    async def collect():
        return "".join(
            [t async for t in provider.stream([LLMMessage("user", "hi")])]
        )

    text = asyncio.run(collect())
    assert text == "Hello"


# ---------------------------------------------------------------------------
# 20. Factory selects OpenRouter (already in test_factory_selects_openrouter)
# ---------------------------------------------------------------------------
# (covered above)


# ---------------------------------------------------------------------------
# Model routing
# ---------------------------------------------------------------------------


def test_model_routing_default():
    provider = OpenRouterProvider(
        key_pool=OpenRouterKeyPool(keys=["sk-or-1"]),
        model="default-m",
        fast_model="fast-m",
        reasoning_model="reason-m",
    )
    assert provider.select_model() == "default-m"
    assert provider.select_model(capability="fast") == "fast-m"
    assert provider.select_model(capability="reasoning") == "reason-m"
    # unknown requested model falls back to default
    assert provider.select_model(requested="totally-arbitrary-model") == "default-m"


# ---------------------------------------------------------------------------
# Health (safe aggregate, no secrets)
# ---------------------------------------------------------------------------


def test_health_safe_aggregate():
    provider = make_provider(["sk-or-1", "sk-or-2"])
    health = provider.health()
    assert health["provider"] == "openrouter"
    assert health["configured_keys"] == 2
    assert health["healthy_keys"] == 2
    assert "sk-or" not in str(health)
    assert health["model"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_keys(provider) -> List[str]:
    transport = provider._client._transport  # type: ignore[attr-defined]
    return [r.headers.get("Authorization", "") for r in transport.requests]


# ===========================================================================
# Optional real integration test — skipped by default
# Requires RUN_OPENROUTER_INTEGRATION_TESTS=true AND a real key.
# Never part of the default suite.
# ===========================================================================


@pytest.mark.skipif(
    os.environ.get("RUN_OPENROUTER_INTEGRATION_TESTS") != "true"
    or not any(
        os.environ.get(f"OPENROUTER_API_KEY_{i}")
        for i in range(1, 6)
    )
    and not os.environ.get("OPENROUTER_API_KEY"),
    reason="Set RUN_OPENROUTER_INTEGRATION_TESTS=true and an OPENROUTER_API_KEY_N to run",
)
async def test_openrouter_real_integration():
    from app.config import settings

    provider = OpenRouterProvider(
        model=settings.openrouter_model,
        key_pool=OpenRouterKeyPool(),
    )
    result = await provider.generate([LLMMessage("user", "Reply with just: OK")])
    assert result.content
    await provider.aclose()
