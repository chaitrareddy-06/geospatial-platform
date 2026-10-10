"""Translate exceptions into one consistent JSON error shape.

Shape: {"error": {"code": "...", "message": "...", "details": {...}}}
"""

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.exceptions import AppError

logger = logging.getLogger(__name__)


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error": {"code": code, "message": message, "details": details or {}}},
        headers=headers,
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    log = logger.error if exc.status_code >= 500 else logger.warning
    log(
        exc.message,
        extra={"error_code": exc.error_code, "status_code": exc.status_code, "path": request.url.path},
    )
    return error_response(exc.status_code, exc.error_code, exc.message, exc.details)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    logger.warning(
        "Request validation failed",
        extra={"error_code": "request_validation_failed", "path": request.url.path},
    )
    return error_response(
        422,
        "request_validation_failed",
        "The request is not valid.",
        {"errors": jsonable_encoder(exc.errors())},
    )


async def http_error_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return error_response(
        exc.status_code,
        f"http_{exc.status_code}",
        str(exc.detail),
        headers=exc.headers,
    )


async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
    # Full traceback goes to the logs; the client only sees a generic message.
    logger.exception(
        "Unhandled exception",
        extra={"error_code": "internal_error", "path": request.url.path},
    )
    return error_response(500, "internal_error", "An unexpected error occurred.")


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(RequestValidationError, validation_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_error_handler)
    app.add_exception_handler(Exception, unhandled_error_handler)