"""Centralised exception -> HTTP response mapping.

Every error response uses one envelope:

    {"error": {"code": "<machine_code>", "message": "<human text>",
               "details": <optional>, "request_id": "<id>"}}

Internal details (SQL, hostnames, credentials, stack traces) are logged
server-side only and never returned to the client.
"""
from __future__ import annotations

import logging
from http import HTTPStatus
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.core.logging import request_id_ctx
from app.database.session import DatabaseNotConfiguredError
from app.integrations.supabase_storage import (
    ImageTooLargeError,
    ImageValidationError,
    StorageError,
    StorageNotFoundError,
    UnsupportedImageTypeError,
)
from app.repositories.base import DomainRuleError, NotFoundError

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Raise from services/handlers to return a specific error to the client.

    `message` is sent to the client, so it must not contain internal details.
    """

    status_code: int = 400
    code: str = "bad_request"

    def __init__(self, message: str, *, status_code: int | None = None, code: str | None = None, details: Any = None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        if code is not None:
            self.code = code
        self.details = details


class ServiceUnavailableError(AppError):
    status_code = 503
    code = "service_unavailable"


class ConflictError(AppError):
    """Duplicate or state conflict the client can resolve (409)."""

    status_code = 409
    code = "conflict"


class InvalidReferenceError(AppError):
    """A request body references a record that does not exist (422)."""

    status_code = 422
    code = "invalid_reference"


# -- OpenAPI documentation of the envelope ----------------------------------
class ErrorBody(BaseModel):
    code: str
    message: str
    details: Any | None = None
    request_id: str


class ErrorEnvelope(BaseModel):
    error: ErrorBody


_ERROR_DESCRIPTIONS = {
    400: "Invalid request",
    404: "Resource not found",
    409: "Duplicate or conflicting resource",
    413: "Image too large",
    415: "Unsupported image type",
    422: "Validation failure or business rule violation",
    502: "Storage service failure",
    503: "Database or storage unavailable",
}


def error_responses(*codes: int) -> dict[int | str, dict[str, Any]]:
    """`responses=` value documenting the error envelope for the given status codes."""
    return {c: {"model": ErrorEnvelope, "description": _ERROR_DESCRIPTIONS.get(c, HTTPStatus(c).phrase)} for c in codes}


_HTTP_CODES = {
    400: "bad_request",
    401: "unauthorized",
    403: "forbidden",
    404: "not_found",
    405: "method_not_allowed",
    409: "conflict",
    413: "payload_too_large",
    415: "unsupported_media_type",
    422: "validation_error",
    429: "too_many_requests",
    500: "internal_error",
    503: "service_unavailable",
}


def error_response(
    status_code: int, code: str, message: str, details: Any = None, headers: dict[str, str] | None = None
) -> JSONResponse:
    body: dict[str, Any] = {"code": code, "message": message, "request_id": request_id_ctx.get()}
    if details is not None:
        body["details"] = details
    return JSONResponse(status_code=status_code, content={"error": body}, headers=headers)


async def _app_error(_: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details)


async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
    code = _HTTP_CODES.get(exc.status_code, "http_error")
    if isinstance(exc.detail, str):
        message, details = exc.detail, None
    else:
        message, details = HTTPStatus(exc.status_code).phrase, exc.detail
    return error_response(exc.status_code, code, message, details, headers=getattr(exc, "headers", None))


async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    # Only location, message and type: the rejected input is not echoed back.
    details = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", "Request validation failed", details)


async def _model_validation_error(_: Request, exc: PydanticValidationError) -> JSONResponse:
    """Models built inside handlers/services (e.g. JSON form fields) failed validation."""
    details = [
        {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type", "")}
        for err in exc.errors()
    ]
    return error_response(422, "validation_error", "Request validation failed", details)


async def _not_found(_: Request, exc: NotFoundError) -> JSONResponse:
    return error_response(404, "not_found", str(exc))


async def _domain_rule(_: Request, exc: DomainRuleError) -> JSONResponse:
    # Messages are written by the repositories and contain no internal data.
    return error_response(422, "domain_rule_violation", str(exc))


async def _integrity(_: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("integrity error: %s", exc.orig)
    return error_response(409, "integrity_conflict", "Request conflicts with existing data")


async def _db_unavailable(_: Request, exc: Exception) -> JSONResponse:
    logger.error("database unavailable: %s", exc)
    return error_response(503, "database_unavailable", "Database is unavailable")


async def _image_invalid(_: Request, exc: ImageValidationError) -> JSONResponse:
    return error_response(422, "invalid_image", str(exc))


async def _image_too_large(_: Request, exc: ImageTooLargeError) -> JSONResponse:
    return error_response(413, "image_too_large", str(exc))


async def _image_unsupported(_: Request, exc: UnsupportedImageTypeError) -> JSONResponse:
    return error_response(415, "unsupported_image_type", str(exc))


async def _storage_not_found(_: Request, exc: StorageNotFoundError) -> JSONResponse:
    return error_response(404, "storage_object_not_found", "Stored object not found")


async def _storage_error(_: Request, exc: StorageError) -> JSONResponse:
    logger.error("storage error (status=%s): %s", exc.status_code, exc)
    return error_response(502, "storage_error", "Storage service request failed")


def register_exception_handlers(app: FastAPI) -> None:
    """Unhandled exceptions are turned into 500s by RequestContextMiddleware."""
    app.add_exception_handler(AppError, _app_error)
    app.add_exception_handler(StarletteHTTPException, _http_error)
    app.add_exception_handler(RequestValidationError, _validation_error)
    app.add_exception_handler(PydanticValidationError, _model_validation_error)
    app.add_exception_handler(NotFoundError, _not_found)
    app.add_exception_handler(DomainRuleError, _domain_rule)
    app.add_exception_handler(IntegrityError, _integrity)
    app.add_exception_handler(OperationalError, _db_unavailable)
    app.add_exception_handler(DatabaseNotConfiguredError, _db_unavailable)
    app.add_exception_handler(ImageValidationError, _image_invalid)
    app.add_exception_handler(ImageTooLargeError, _image_too_large)
    app.add_exception_handler(UnsupportedImageTypeError, _image_unsupported)
    app.add_exception_handler(StorageNotFoundError, _storage_not_found)
    app.add_exception_handler(StorageError, _storage_error)
