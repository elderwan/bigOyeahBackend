import json
import logging
from typing import Any
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.request_context import request_id_context
from app.schemas.responses import BaseResponse, utc_timestamp

logger = logging.getLogger(__name__)


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = self._request_id(scope)
        scope.setdefault("state", {})["request_id"] = request_id
        token = request_id_context.set(request_id)
        body = bytearray()
        response_started: Message | None = None

        async def send_wrapper(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = message
                return
            if message["type"] == "http.response.body":
                body.extend(message.get("body", b""))
                if not message.get("more_body", False):
                    await self._send_enveloped_response(
                        response_started,
                        bytes(body),
                        request_id,
                        send,
                    )
                return
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            if response_started is None:
                logger.exception("Unhandled exception request_id=%s", request_id)
                payload = BaseResponse(
                    success=False,
                    code=500,
                    message="Internal server error",
                    errors=[
                        {
                            "field": "request",
                            "code": "internal_server_error",
                            "message": "An unexpected error occurred",
                        }
                    ],
                    requestId=request_id,
                    timestamp=utc_timestamp(),
                ).model_dump(mode="json")
                response_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
                await send(
                    {
                        "type": "http.response.start",
                        "status": 500,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(response_body)).encode("ascii")),
                            (b"x-request-id", request_id.encode("utf-8")),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": response_body})
            return
        finally:
            request_id_context.reset(token)

    @staticmethod
    def _request_id(scope: Scope) -> str:
        for name, value in scope.get("headers", []):
            if name.lower() == b"x-request-id" and value:
                return value.decode("utf-8", errors="replace")
        return str(uuid4())

    async def _send_enveloped_response(
        self,
        response_started: Message | None,
        body: bytes,
        request_id: str,
        send: Send,
    ) -> None:
        if response_started is None:
            return

        status = int(response_started["status"])
        headers = list(response_started.get("headers", []))
        content_type = next(
            (
                value.decode("latin-1")
                for name, value in headers
                if name.lower() == b"content-type"
            ),
            "",
        )
        if status == 204 or "application/json" not in content_type:
            await send(response_started)
            await send({"type": "http.response.body", "body": body})
            return

        try:
            payload: Any = json.loads(body) if body else None
        except json.JSONDecodeError:
            payload = body.decode("utf-8", errors="replace")

        if not (
            isinstance(payload, dict)
            and {"success", "code", "message", "requestId", "timestamp"}.issubset(
                payload
            )
        ):
            payload = BaseResponse(
                success=200 <= status < 400,
                code=status,
                message="Success" if 200 <= status < 400 else "Request failed",
                data=payload,
                requestId=request_id,
                timestamp=utc_timestamp(),
            ).model_dump(mode="json")

        response_body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        filtered_headers = [
            (name, value)
            for name, value in headers
            if name.lower() not in {b"content-length", b"x-request-id"}
        ]
        filtered_headers.extend(
            [
                (b"content-length", str(len(response_body)).encode("ascii")),
                (b"x-request-id", request_id.encode("utf-8")),
            ]
        )
        await send({"type": "http.response.start", "status": status, "headers": filtered_headers})
        await send({"type": "http.response.body", "body": response_body})
