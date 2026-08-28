"""Authentication for calls to the backend and for this engine's own API.

The backend remains authoritative: the engine never lets the user inject
identity or scope; it forwards the authenticated identity it was given.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import httpx

from app.config import settings


def _auth_headers() -> Dict[str, str]:
    headers: Dict[str, str] = {"Accept": "application/json"}
    if settings.backend_api_key:
        headers["X-API-Key"] = settings.backend_api_key
    if settings.backend_jwt_token:
        headers["Authorization"] = f"Bearer {settings.backend_jwt_token}"
    return headers


def build_forwarded_headers(
    user_id: Optional[str] = None,
    user_role: Optional[str] = None,
    permissions: Optional[List[str]] = None,
    request_id: Optional[str] = None,
) -> Dict[str, str]:
    """Attach the engine-established identity to a backend call.

    Identity is established by the engine's own auth boundary (API key /
    JWT on this service). It is never taken from free-form user text.
    """
    headers = _auth_headers()
    from app.observability.context import request_id_var

    rid = request_id or request_id_var.get() or "unknown"
    headers["X-Request-ID"] = rid
    if user_id:
        headers["X-User-Id"] = user_id
    if user_role:
        headers["X-User-Role"] = user_role
    if permissions:
        headers["X-Permissions"] = ",".join(permissions)
    return headers
