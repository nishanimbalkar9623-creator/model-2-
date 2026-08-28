"""HTTP client for talking to the AOS Backend API.

Responsibilities:
- authentication headers (API key / JWT)
- timeouts
- retries ONLY for safe (GET) operations
- structured errors
- request IDs
- logging (sanitized)

All business truth lives in the backend. This client never bypasses auth or
scope — it only forwards validated identity headers.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.backend.auth import build_forwarded_headers
from app.config import settings
from app.observability.context import request_id_var
from app.observability.logging import get_logger

logger = get_logger("backend_client")

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


class BackendError(Exception):
    """Base class for backend communication errors."""

    def __init__(
        self,
        message: str,
        status_code: Optional[int] = None,
        request_id: Optional[str] = None,
    ):
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.request_id = request_id


class BackendAuthError(BackendError):
    pass


class BackendPermissionError(BackendError):
    pass


class BackendNotFoundError(BackendError):
    pass


class BackendConflictError(BackendError):
    pass


class BackendValidationError(BackendError):
    pass


class BackendRateLimitedError(BackendError):
    pass


class BackendServerError(BackendError):
    pass


class BackendTimeoutError(BackendError):
    pass


def _error_for_status(
    status: int, message: str, request_id: Optional[str] = None
) -> BackendError:
    if status == 401:
        return BackendAuthError(message, status, request_id)
    if status == 403:
        return BackendPermissionError(message, status, request_id)
    if status in (400, 422):
        return BackendValidationError(message, status, request_id)
    if status == 404:
        return BackendNotFoundError(message, status, request_id)
    if status == 409:
        return BackendConflictError(message, status, request_id)
    if status == 429:
        return BackendRateLimitedError(message, status, request_id)
    if status >= 500:
        return BackendServerError(message, status, request_id)
    return BackendError(message, status, request_id)


class BackendClient:
    """Thread-safe-ish async client.

    A single shared httpx.AsyncClient instance is reused to avoid connection
    churn. In tests, replace this object with a fake.
    """

    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.backend_base_url).rstrip("/")
        self.timeout = settings.backend_timeout_seconds
        self.max_retries = settings.backend_max_retries
        self._client = httpx.AsyncClient(timeout=self.timeout, follow_redirects=True)

    async def aclose(self) -> None:
        await self._client.aclose()

    @staticmethod
    def _headers(
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Dict[str, str]:
        return build_forwarded_headers(user_id, user_role, permissions)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        user_id: Optional[str] = None,
        user_role: Optional[str] = None,
        permissions: Optional[List[str]] = None,
    ) -> Any:
        url = f"{self.base_url}{path}"
        headers = self._headers(user_id, user_role, permissions)
        rid = request_id_var.get() or "unknown"
        logger.debug("backend %s %s rid=%s", method, path, rid)

        retries = self.max_retries if method in SAFE_METHODS else 0
        attempt = 0
        while True:
            try:
                resp = await self._client.request(
                    method, url, params=params, json=json, headers=headers
                )
            except httpx.TimeoutException:
                logger.warning("backend timeout %s %s", method, path)
                if attempt < retries:
                    attempt += 1
                    continue
                raise BackendTimeoutError(f"Backend timed out for {path}")
            except httpx.HTTPError as exc:
                logger.warning("backend http error %s %s: %s", method, path, exc)
                if attempt < retries:
                    attempt += 1
                    continue
                raise BackendServerError(f"Backend unreachable: {path}")

            if resp.is_success:
                try:
                    return resp.json() if resp.content else None
                except ValueError:
                    return resp.text

            # non-2xx — never retry mutations, and only retry GETs above
            try:
                payload = resp.json()
                detail = payload.get("detail") or payload.get("message") or payload
            except ValueError:
                detail = resp.text
            err = _error_for_status(resp.status_code, str(detail), rid)
            logger.warning(
                "backend error %s %s status=%s", method, path, resp.status_code
            )
            raise err

    async def get(self, path: str, **kw) -> Any:
        return await self._request("GET", path, **kw)

    async def post(self, path: str, **kw) -> Any:
        return await self._request("POST", path, **kw)

    async def patch(self, path: str, **kw) -> Any:
        return await self._request("PATCH", path, **kw)
