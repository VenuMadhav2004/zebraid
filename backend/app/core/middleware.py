"""Request context middleware: request id, access log, last-resort 500 handler.

It sits inside CORSMiddleware, so even 500 responses carry CORS headers and the
browser can read the error envelope.
"""
from __future__ import annotations

import logging
import re
import time
import uuid

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_response
from app.core.logging import request_id_ctx

logger = logging.getLogger("app.request")

REQUEST_ID_HEADER = "X-Request-ID"
_VALID_REQUEST_ID = re.compile(r"^[A-Za-z0-9._\-]{1,64}$")


def _incoming_request_id(scope: Scope) -> str | None:
    for name, value in scope.get("headers", []):
        if name == b"x-request-id":
            candidate = value.decode("latin-1")
            return candidate if _VALID_REQUEST_ID.match(candidate) else None
    return None


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp):
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _incoming_request_id(scope) or uuid.uuid4().hex
        token = request_id_ctx.set(request_id)
        start = time.perf_counter()
        status_code = 500
        response_started = False

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code, response_started
            if message["type"] == "http.response.start":
                response_started = True
                status_code = message["status"]
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            logger.exception("unhandled error on %s %s", scope.get("method"), scope.get("path"))
            if response_started:
                raise
            response = error_response(500, "internal_error", "Internal server error")
            await response(scope, receive, send_wrapper)
        finally:
            # Path only: query strings may carry tokens.
            logger.info(
                "%s %s -> %s (%.1f ms)",
                scope.get("method"),
                scope.get("path"),
                status_code,
                (time.perf_counter() - start) * 1000,
            )
            request_id_ctx.reset(token)
