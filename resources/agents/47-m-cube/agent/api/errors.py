from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from models.common import ApiEnvelope, ErrorInfo, SessionStatus


class ApiError(Exception):
    """Application exception mapped to unified error envelope + status code."""

    def __init__(
        self,
        *,
        http_status: int,
        code: str,
        message: str,
        session_id: str,
        retryable: bool = False,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.http_status = http_status
        self.code = code
        self.message = message
        self.session_id = session_id
        self.retryable = retryable
        self.details = details or {}


def _error_response(
    *,
    http_status: int,
    session_id: str,
    code: str,
    message: str,
    retryable: bool,
    details: dict[str, Any],
) -> JSONResponse:
    envelope = ApiEnvelope(
        request_id=str(uuid4()),
        session_id=session_id,
        status=SessionStatus.failed,
        data=None,
        error=ErrorInfo(
            code=code,
            message=message,
            details=details,
            retryable=retryable,
        ),
    )
    return JSONResponse(status_code=http_status, content=envelope.model_dump(mode="json"))


def register_exception_handlers(app: FastAPI) -> None:
    """Register global handlers so every API failure follows ApiEnvelope contract."""

    @app.exception_handler(ApiError)
    async def _handle_api_error(_: Request, exc: ApiError) -> JSONResponse:
        return _error_response(
            http_status=exc.http_status,
            session_id=exc.session_id,
            code=exc.code,
            message=exc.message,
            retryable=exc.retryable,
            details=exc.details,
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        session_id = request.path_params.get("session_id", "unknown")
        return _error_response(
            http_status=400,
            session_id=session_id,
            code="E400_INVALID_INPUT",
            message="Request validation failed.",
            retryable=False,
            details={"errors": exc.errors()},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _handle_http_exception(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        session_id = request.path_params.get("session_id", "unknown")
        code = "E500_INTERNAL_ERROR"
        if exc.status_code == 404:
            code = "E404_SESSION_NOT_FOUND"
        elif exc.status_code == 401:
            code = "E401_UNAUTHORIZED"
        return _error_response(
            http_status=exc.status_code,
            session_id=session_id,
            code=code,
            message=str(exc.detail),
            retryable=False,
            details={},
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected(_: Request, exc: Exception) -> JSONResponse:
        return _error_response(
            http_status=500,
            session_id="unknown",
            code="E500_INTERNAL_ERROR",
            message=str(exc),
            retryable=False,
            details={},
        )
