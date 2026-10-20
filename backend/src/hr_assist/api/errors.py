import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from hr_assist.api.rate_limit import RateLimited
from hr_assist.api.request_id import request_id_var
from hr_assist.errors import UpstreamError

logger = logging.getLogger("hr_assist.errors")


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        headers=headers,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or [],
                "request_id": request_id_var.get(),
            }
        },
    )


async def _validation_error(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)
    details = [
        {"loc": list(err["loc"]), "msg": err["msg"], "type": err["type"]} for err in exc.errors()
    ]
    return error_response(422, "validation_error", "The request is invalid.", details)


async def _upstream_error(_: Request, exc: Exception) -> JSONResponse:
    return error_response(503, "upstream_unavailable", str(exc))


async def _rate_limited(_: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RateLimited)
    return error_response(
        429, "rate_limited", str(exc), headers={"Retry-After": str(exc.retry_after_seconds)}
    )


class InternalErrorMiddleware:
    """Answers an unhandled exception with a 500 in the shared format.

    It runs inside the other middleware, unlike Starlette's own 500 handler, so the
    response still gets its request ID, CORS and Cache-Control headers.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        response_started = False

        async def send_tracking_start(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
            await send(message)

        try:
            await self.app(scope, receive, send_tracking_start)
        except Exception:
            logger.exception("Unhandled error on %s %s", scope["method"], scope["path"])
            if response_started:
                raise
            response = error_response(
                500, "internal_error", "Something went wrong. Please try again."
            )
            await response(scope, receive, send)


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(UpstreamError, _upstream_error)
    app.add_exception_handler(RateLimited, _rate_limited)
