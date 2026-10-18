from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from hr_assist.api.request_id import request_id_var
from hr_assist.errors import UpstreamError


def error_response(
    status_code: int, code: str, message: str, details: list[dict[str, Any]] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
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


def register_error_handlers(app: FastAPI) -> None:
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(UpstreamError, _upstream_error)
