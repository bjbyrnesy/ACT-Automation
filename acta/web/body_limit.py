"""ASGI body-size limit that counts bytes as they arrive.

Starlette's ``request.form()`` spools a whole multipart body to disk before any
route code runs, so a chunked upload without ``Content-Length`` could fill the
disk. This middleware wraps ``receive`` for selected paths, counts body bytes,
and aborts with HTTP 400 as soon as the cap is crossed.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from starlette.types import ASGIApp, Message, Receive, Scope, Send

# Multipart boundaries and form fields add a little on top of the file bytes.
MULTIPART_OVERHEAD_BYTES = 1024 * 1024


class BodyTooLarge(Exception):
    """Raised from ``receive`` once the request body exceeds the limit."""


class BodyLimitMiddleware:
    """Reject request bodies over ``limit()`` bytes on ``paths`` (POST only)."""

    def __init__(
        self,
        app: ASGIApp,
        *,
        paths: frozenset[str],
        limit: Callable[[], int],
    ) -> None:
        self.app = app
        self.paths = paths
        self.limit = limit

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if (
            scope["type"] != "http"
            or scope["method"] != "POST"
            or scope["path"] not in self.paths
        ):
            await self.app(scope, receive, send)
            return
        limit = self.limit()
        declared = dict(scope["headers"]).get(b"content-length", b"")
        if declared.isdigit() and int(declared) > limit:
            await self._reject(send)
            return
        total = 0
        started = False

        async def counting_receive() -> Message:
            nonlocal total
            message = await receive()
            if message["type"] == "http.request":
                total += len(message.get("body", b""))
                if total > limit:
                    raise BodyTooLarge
            return message

        async def tracking_send(message: Message) -> None:
            nonlocal started
            if message["type"] == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, counting_receive, tracking_send)
        except BodyTooLarge:
            if started:
                raise
            await self._reject(send)

    @staticmethod
    async def _reject(send: Send) -> None:
        payload: dict[str, Any] = {
            "detail": "archive exceeds 10GB limit",
            "fields": {"file": "too large"},
        }
        body = json.dumps(payload).encode()
        await send(
            {
                "type": "http.response.start",
                "status": 400,
                "headers": [
                    (b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode()),
                    (b"connection", b"close"),
                ],
            }
        )
        await send({"type": "http.response.body", "body": body})
