"""Request logging middleware for FastAPI."""

from __future__ import annotations

import uuid
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

from app.observability.context import (
    client_id_var,
    conversation_id_var,
    request_id_var,
    user_id_var,
)
from app.observability.logging import get_logger


logger = get_logger("request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Middleware to log requests with context."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate or extract request ID
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request_id_var.set(req_id)
        
        # Extract other context from headers
        user_id = request.headers.get("X-User-ID")
        if user_id:
            user_id_var.set(user_id)
        
        client_id = request.headers.get("X-Client-ID")
        if client_id:
            client_id_var.set(client_id)
        
        conv_id = request.headers.get("X-Conversation-ID")
        if conv_id:
            conversation_id_var.set(conv_id)

        # Log request start
        logger.info(
            "request_start",
            extra={
                "request_id": req_id,
                "method": request.method,
                "path": request.url.path,
                "user_id": user_id,
                "client_id": client_id,
                "conversation_id": conv_id,
            }
        )

        try:
            response = await call_next(request)
            
            # Log response
            logger.info(
                "request_complete",
                extra={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "status_code": response.status_code,
                }
            )
            
            response.headers["X-Request-ID"] = req_id
            return response
            
        except Exception as e:
            logger.error(
                "request_error",
                extra={
                    "request_id": req_id,
                    "method": request.method,
                    "path": request.url.path,
                    "error": str(e),
                }
            )
            raise