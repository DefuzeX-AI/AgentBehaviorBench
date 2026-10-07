"""Response and exception helpers that preserve the Java API contract.

Spring wrapped most REST responses as `{code,data,msg}`. The FastAPI rewrite
uses these helpers at route boundaries so existing frontends can keep parsing
responses the same way.
"""

from collections.abc import Callable
from datetime import date, datetime
from enum import Enum
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import SQLAlchemyError


SUCCESS_MESSAGE = "\u8bf7\u6c42\u6210\u529f"


class AppError(Exception):
    """Business exception that should be returned in the Java response envelope."""

    def __init__(self, message: str, code: int = 500) -> None:
        self.message = message
        self.code = code
        super().__init__(message)


class IllegalArgumentError(ValueError):
    """Mirrors Java IllegalArgumentException behavior for compatibility."""


def unwrap_enum(value: Any) -> Any:
    """Serialize enums and datetime values into JSON-friendly scalar values."""

    if isinstance(value, Enum):
        return value.name
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def to_camel(name: str) -> str:
    """Convert database snake_case column names back to Java camelCase fields."""

    parts = name.split("_")
    return parts[0] + "".join(part[:1].upper() + part[1:] for part in parts[1:])


def to_java_dict(value: Any) -> Any:
    """Recursively serialize SQLAlchemy/Pydantic objects into Java-style JSON."""

    if value is None:
        return None
    if isinstance(value, list):
        return [to_java_dict(item) for item in value]
    if isinstance(value, tuple):
        return [to_java_dict(item) for item in value]
    if isinstance(value, dict):
        return {str(k): to_java_dict(v) for k, v in value.items()}
    if hasattr(value, "model_dump"):
        return to_java_dict(value.model_dump(by_alias=True))
    if hasattr(value, "__table__"):
        return {
            to_camel(column.name): to_java_dict(getattr(value, column.name))
            for column in value.__table__.columns
        }
    return unwrap_enum(value)


def success(data: Any = None) -> dict[str, Any]:
    return {"code": 200, "data": to_java_dict(data), "msg": SUCCESS_MESSAGE}


def error(message: str, code: int = 500) -> dict[str, Any]:
    return {"code": code, "data": None, "msg": message}


def json_success(data: Any = None) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(success(data)))


def json_error(message: str, code: int = 500, status_code: int = 200) -> JSONResponse:
    return JSONResponse(content=jsonable_encoder(error(message, code)), status_code=status_code)


def install_exception_handlers(app: FastAPI) -> None:
    """Register global handlers that emulate Spring's response advice."""

    @app.exception_handler(AppError)
    async def app_error_handler(_: Request, exc: AppError) -> JSONResponse:
        return json_error(exc.message, exc.code)

    @app.exception_handler(ValueError)
    @app.exception_handler(IllegalArgumentError)
    async def value_error_handler(_: Request, exc: Exception) -> JSONResponse:
        return json_error(str(exc) or "\u53c2\u6570\u9519\u8bef")

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        return json_error(str(exc) or "\u53c2\u6570\u9519\u8bef")

    @app.exception_handler(SQLAlchemyError)
    async def sqlalchemy_error_handler(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        return json_error(str(exc) or "\u6570\u636e\u5e93\u64cd\u4f5c\u5931\u8d25")

    @app.exception_handler(Exception)
    async def generic_error_handler(_: Request, exc: Exception) -> JSONResponse:
        return json_error(str(exc) or "\u670d\u52a1\u5668\u5f02\u5e38")

RouteHandler = Callable[..., Any]
