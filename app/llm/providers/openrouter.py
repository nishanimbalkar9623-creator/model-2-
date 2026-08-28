"""OpenRouter provider.

Uses OpenRouter's OpenAI-compatible chat completions API with an
OpenRouterKeyPool for multiple API keys, automatic key rotation and
cooldown on temporary failures, exponential backoff, configurable model
routing, and full support for the engine's tool-calling + streaming
abstractions.

The rest of the application only sees ``LLMProvider`` / ``LLMResult`` /
``LLMMessage`` / ``ToolSpec``; it never knows OpenRouter is in use.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import time
import uuid
from typing import Any, AsyncIterator, Dict, List, Optional, Tuple

import httpx

from app.config import settings
from app.llm.base import LLMMessage, LLMProvider, LLMResult, ToolSpec
from app.llm.errors import (
    LLMAuthenticationError,
    LLMError,
    LLMInvalidRequestError,
    LLMProviderError,
    LLMRateLimitError,
    LLMTimeoutError,
    LLMUnavailableError,
)
from app.llm.key_pool import OpenRouterKeyPool, mask_key

logger = logging.getLogger("aos.openrouter")

CHAT_PATH = "/chat/completions"


class OpenRouterProvider(LLMProvider):
    name = "openrouter"

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        fast_model: Optional[str] = None,
        reasoning_model: Optional[str] = None,
        app_name: Optional[str] = None,
        http_referer: Optional[str] = None,
        max_retries: Optional[int] = None,
        key_pool: Optional[OpenRouterKeyPool] = None,
        request_id_header: Optional[str] = None,
    ):
        self.base_url = (base_url or settings.openrouter_base_url).rstrip("/")
        self.model = model or settings.openrouter_model
        self.fast_model = fast_model or settings.openrouter_fast_model
        self.reasoning_model = reasoning_model or settings.openrouter_reasoning_model
        self.app_name = app_name or settings.openrouter_app_name
        self.http_referer = http_referer or settings.openrouter_http_referer
        self.max_retries = int(max_retries if max_retries is not None else settings.max_llm_retries)
        self.request_id_header = request_id_header or settings.openrouter_request_id_header

        if key_pool is not None:
            self.key_pool = key_pool
        else:
            self.key_pool = OpenRouterKeyPool()

        if not self.key_pool.has_keys():
            raise LLMUnavailableError(
                "No OpenRouter API keys configured. Set OPENROUTER_API_KEY_1..N "
                "(or OPENROUTER_API_KEY)."
            )

        # Reusable HTTP client managed across the provider lifetime.
        self._client: Optional[httpx.AsyncClient] = None
        self._client_lock = asyncio.Lock()

    # ---- Lifecycle ----

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            async with self._client_lock:
                if self._client is None or self._client.is_closed:
                    self._client = httpx.AsyncClient(
                        timeout=httpx.Timeout(
                            connect=settings.openrouter_connect_timeout_seconds,
                            read=settings.openrouter_read_timeout_seconds,
                            write=settings.openrouter_connect_timeout_seconds,
                            pool=settings.openrouter_connect_timeout_seconds,
                        ),
                    )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ---- Model routing ----

    def select_model(self, *, capability: Optional[str] = None, requested: Optional[str] = None) -> str:
        """Map a safe capability/request to a model.

        ``requested`` is only honoured if it matches one of the configured
        model slots — arbitrary user strings are never passed to the API
        directly.
        """
        if requested:
            if requested == self.fast_model:
                return requested
            if requested == self.reasoning_model:
                return requested
            if requested == self.model:
                return requested
        if capability == "fast" and self.fast_model:
            return self.fast_model
        if capability == "reasoning" and self.reasoning_model:
            return self.reasoning_model
        return self.model

    # ---- Request helpers ----

    def _extra_headers(self, request_id: Optional[str] = None) -> Dict[str, str]:
        headers = {
            "X-Title": self.app_name,
        }
        if self.http_referer:
            headers["HTTP-Referer"] = self.http_referer
        if request_id:
            headers[self.request_id_header] = request_id
        return headers

    def _to_openai(self, messages: List[LLMMessage]) -> List[Dict[str, Any]]:
        out: List[Dict[str, Any]] = []
        for m in messages:
            if m.role == "tool":
                # Convert tool role into OpenAI's expected shape.
                out.append({"role": "user", "content": m.content})
            else:
                out.append({"role": m.role, "content": m.content})
        return out

    def parse_tool_calls(self, message: Dict[str, Any]) -> List[Dict[str, Any]]:
        tool_calls: List[Dict[str, Any]] = []
        for tc in message.get("tool_calls", []) or []:
            fn = tc.get("function", {})
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args)
            except Exception:
                args = {}
            tool_calls.append({"name": fn.get("name"), "arguments": args})
        return tool_calls

    async def _classify_http_error(
        self,
        status_code: int,
        body: Any,
        key_index: Optional[int],
    ) -> LLMError:
        message = _extract_error_message(body) or f"OpenRouter returned HTTP {status_code}"
        if status_code in (401, 403):
            return LLMAuthenticationError(
                f"OpenRouter authentication failed (key {key_index}): {message}",
                status_code=status_code,
            )
        if status_code == 429:
            return LLMRateLimitError(
                f"OpenRouter rate limit exceeded (key {key_index}): {message}",
                status_code=status_code,
            )
        if 500 <= status_code <= 599:
            return LLMProviderError(
                f"OpenRouter server error (key {key_index}): {message}",
                status_code=status_code,
                retryable=True,
            )
        if 400 <= status_code < 500:
            return LLMInvalidRequestError(
                f"OpenRouter rejected request (key {key_index}): {message}",
                status_code=status_code,
            )
        return LLMProviderError(message, status_code=status_code)

    # ---- Core generate with retry + key rotation ----

    async def generate(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> LLMResult:
        capability = kwargs.get("capability")
        model = self.select_model(capability=capability, requested=kwargs.get("model"))
        request_id = kwargs.get("request_id") or uuid.uuid4().hex[:12]
        headers = self._extra_headers(request_id)

        body = self._build_body(messages, tools, temperature, max_tokens, model)
        client = await self._get_client()

        attempts = 0
        max_attempts = min(self.max_retries, self.key_pool.total) or 1
        last_error: Optional[LLMError] = None

        while attempts < max_attempts:
            attempts += 1
            slot = await self.key_pool.acquire_healthy()
            if slot is None:
                if not self.key_pool.has_keys():
                    raise LLMUnavailableError("No OpenRouter keys configured.")
                # all keys cooling down — brief backoff then retry
                await asyncio.sleep(min(0.5 * (2 ** (attempts - 1)), 4.0))
                continue

            auth = {"Authorization": f"Bearer {slot.key}"}
            try:
                resp = await client.post(
                    f"{self.base_url}{CHAT_PATH}",
                    headers={**headers, **auth},
                    json=body,
                )
            except httpx.TimeoutException:
                self.key_pool.mark_failure(slot.index, "timeout")
                last_error = LLMTimeoutError(f"OpenRouter request timed out (key {slot.index})")
                logger.warning("OpenRouter request timed out on key %d (attempt %d)", slot.index, attempts)
                await _backoff(attempts, retry_after=None)
                continue
            except httpx.HTTPError as exc:  # connection errors, etc.
                self.key_pool.mark_failure(slot.index, "connect")
                last_error = LLMProviderError(
                    f"OpenRouter connectivity error (key {slot.index}): {exc}",
                    retryable=True,
                )
                logger.warning("OpenRouter connectivity error on key %d (attempt %d)", slot.index, attempts)
                await _backoff(attempts, retry_after=None)
                continue

            if resp.status_code in (200, 201):
                self.key_pool.mark_recovered(slot.index)
                try:
                    data = resp.json()
                except Exception:
                    raise LLMProviderError("OpenRouter returned malformed JSON")
                return self._parse_completion(data)

            # Non-2xx
            try:
                error_body = resp.json()
            except Exception:
                error_body = resp.text[:1000]
            retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
            llm_error = await self._classify_http_error(resp.status_code, error_body, slot.index)

            last_error = llm_error
            if llm_error.retryable or isinstance(llm_error, LLMRateLimitError):
                kind = "429" if isinstance(llm_error, LLMRateLimitError) else str(resp.status_code)
                self.key_pool.mark_failure(slot.index, kind, retry_after=retry_after)
                logger.warning(
                    "OpenRouter key %d failed with %s (attempt %d)",
                    slot.index, resp.status_code, attempts,
                )
                await _backoff(attempts, retry_after=retry_after)
                continue
            if isinstance(llm_error, LLMAuthenticationError):
                self.key_pool.mark_failure(slot.index, "401")
                logger.warning("OpenRouter key %d rejected (401/403)", slot.index)
                await _backoff(attempts, retry_after=None)
                if attempts >= max_attempts:
                    break
                continue
            # 400-class: do not blindly retry.
            raise llm_error

        if not self.key_pool.has_keys():
            raise LLMUnavailableError("No OpenRouter keys configured.")
        if last_error is not None:
            raise last_error
        raise LLMUnavailableError("All OpenRouter keys are currently unavailable.")

    # ---- Body / parsing ----

    def _build_body(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]],
        temperature: float,
        max_tokens: Optional[int],
        model: str,
    ) -> Dict[str, Any]:
        body: Dict[str, Any] = {
            "model": model,
            "messages": self._to_openai(messages),
            "temperature": temperature,
        }
        if max_tokens:
            body["max_tokens"] = max_tokens
        if tools:
            body["tools"] = [self.build_tool_spec(t) for t in tools]
            body["tool_choice"] = "auto"
        return body

    def _parse_completion(self, data: Dict[str, Any]) -> LLMResult:
        choices = data.get("choices") or []
        if not choices:
            raise LLMProviderError("OpenRouter returned no choices")
        choice = choices[0]
        message = choice.get("message", {})
        content = message.get("content") or ""
        tool_calls = self.parse_tool_calls(message)
        usage = data.get("usage", {})
        model = data.get("model")
        return LLMResult(
            content=content,
            tool_calls=tool_calls,
            model=model,
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
        )

    # ---- Streaming ----

    async def stream(
        self,
        messages: List[LLMMessage],
        tools: Optional[List[ToolSpec]] = None,
        temperature: float = 0.2,
        max_tokens: Optional[int] = None,
        **kwargs: Any,
    ) -> AsyncIterator[str]:
        capability = kwargs.get("capability")
        model = self.select_model(capability=capability, requested=kwargs.get("model"))
        request_id = kwargs.get("request_id") or uuid.uuid4().hex[:12]
        headers = self._extra_headers(request_id)
        body = self._build_body(messages, tools, temperature, max_tokens, model)
        body["stream"] = True

        client = await self._get_client()
        attempts = 0
        max_attempts = min(self.max_retries, self.key_pool.total) or 1

        while attempts < max_attempts:
            attempts += 1
            slot = await self.key_pool.acquire_healthy()
            if slot is None:
                if not self.key_pool.has_keys():
                    raise LLMUnavailableError("No OpenRouter keys configured.")
                await asyncio.sleep(min(0.5 * (2 ** (attempts - 1)), 4.0))
                continue

            auth = {"Authorization": f"Bearer {slot.key}"}
            try:
                async with client.stream(
                    "POST",
                    f"{self.base_url}{CHAT_PATH}",
                    headers={**headers, **auth},
                    json=body,
                ) as resp:
                    if resp.status_code not in (200, 201):
                        error_body = (await resp.aread()).decode("utf-8", "ignore")
                        llm_error = await self._classify_http_error(resp.status_code, error_body, slot.index)
                        retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                        if llm_error.retryable or isinstance(llm_error, LLMRateLimitError):
                            self.key_pool.mark_failure(
                                slot.index,
                                "429" if isinstance(llm_error, LLMRateLimitError) else str(resp.status_code),
                                retry_after=retry_after,
                            )
                            await _backoff(attempts, retry_after=retry_after)
                            continue
                        if isinstance(llm_error, LLMAuthenticationError):
                            self.key_pool.mark_failure(slot.index, "401")
                            await _backoff(attempts, retry_after=None)
                            if attempts >= max_attempts:
                                raise llm_error
                            continue
                        raise llm_error

                    self.key_pool.mark_recovered(slot.index)
                    async for line in resp.aiter_lines():
                        if not line or not line.startswith("data:"):
                            continue
                        payload = line[5:].strip()
                        if payload == "[DONE]":
                            return
                        try:
                            chunk = json.loads(payload)
                        except Exception:
                            continue
                        choices = chunk.get("choices") or []
                        if not choices:
                            continue
                        delta = choices[0].get("delta", {})
                        content = delta.get("content") or ""
                        if content:
                            yield content
                    return

            except httpx.TimeoutException:
                self.key_pool.mark_failure(slot.index, "timeout")
                logger.warning("OpenRouter stream timed out on key %d (attempt %d)", slot.index, attempts)
                await _backoff(attempts, retry_after=None)
            except httpx.HTTPError as exc:
                self.key_pool.mark_failure(slot.index, "connect")
                logger.warning("OpenRouter stream HTTP error on key %d (attempt %d)", slot.index, attempts)
                await _backoff(attempts, retry_after=None)

        raise LLMUnavailableError("All OpenRouter keys are currently unavailable for streaming.")

    # ---- Simple completion ----

    async def complete(self, prompt: str, **kwargs: Any) -> str:
        result = await self.generate(
            [LLMMessage("user", prompt)],
            temperature=0.0,
            **kwargs,
        )
        return result.content

    # ---- Health ----

    def health(self) -> Dict[str, Any]:
        pool = self.key_pool.health()
        return {
            "provider": self.name,
            "ok": self.key_pool.has_keys() and self.key_pool.healthy > 0,
            **pool,
            "model": self.model,
        }


# ---- Helpers ----


def _extract_error_message(body: Any) -> Optional[str]:
    try:
        if isinstance(body, dict):
            err = body.get("error")
            if isinstance(err, dict):
                return str(err.get("message") or err.get("code") or "")
            if isinstance(err, str):
                return err
            msg = body.get("message")
            if msg:
                return str(msg)
    except Exception:
        pass
    return None


def _parse_retry_after(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        return float(value)
    except Exception:
        return None


async def _backoff(attempt: int, retry_after: Optional[float] = None) -> None:
    """Exponential backoff, honouring Retry-After when available."""
    if retry_after is not None and retry_after > 0:
        delay = min(retry_after, 30.0)
    else:
        delay = min(0.5 * (2 ** (attempt - 1)), 8.0)
    await asyncio.sleep(delay)


__all__ = ["OpenRouterProvider", "CHAT_PATH"]
