import logging
from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.request_context import get_request_id
from app.schemas.responses import ErrorDetail, error_response

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    return getattr(request.state, "request_id", None) or get_request_id() or "unknown"


def _validation_error(error: dict[str, Any]) -> ErrorDetail:
    location = error.get("loc", ())
    field = ".".join(str(part) for part in location if part not in {"body", "query", "path"})
    return ErrorDetail(
        field=field or "request",
        code=str(error.get("type", "validation_error")),
        message=str(error.get("msg", "Invalid request")),
    )


async def request_validation_exception_handler(
    request: Request, exc: RequestValidationError
) -> JSONResponse:
    response = error_response(
        code=422,
        message="Request validation failed",
        errors=[_validation_error(error) for error in exc.errors()],
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=422,
        content=response.model_dump(mode="json"),
        headers={"X-Request-ID": _request_id(request)},
    )


async def http_exception_handler(
    request: Request, exc: StarletteHTTPException
) -> JSONResponse:
    detail = exc.detail if isinstance(exc.detail, str) else "Request failed"
    response = error_response(
        code=exc.status_code,
        message=detail,
        errors=[
            ErrorDetail(field="request", code=f"http_{exc.status_code}", message=detail)
        ],
        request_id=_request_id(request),
    )
    return JSONResponse(
        status_code=exc.status_code,
        content=response.model_dump(mode="json"),
        headers={"X-Request-ID": _request_id(request)},
    )


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.exception("Unhandled exception request_id=%s", request_id, exc_info=exc)
    response = error_response(
        code=500,
        message="Internal server error",
        errors=[
            ErrorDetail(
                field="request",
                code="internal_server_error",
                message="An unexpected error occurred",
            )
        ],
        request_id=request_id,
    )
    return JSONResponse(
        status_code=500,
        content=response.model_dump(mode="json"),
        headers={"X-Request-ID": request_id},
    )
