"""Authentication helpers for internal compatibility endpoints."""

from fastapi import Header

from app.core.config import get_settings
from app.core.responses import AppError


def require_internal_ai_token(authorization: str | None = Header(default=None)) -> None:
    """Validate the bearer token used by compatibility AI endpoints."""

    expected = f"Bearer {get_settings().internal_ai_token}"
    if not authorization or authorization != expected:
        raise AppError("\u672a\u6388\u6743")
