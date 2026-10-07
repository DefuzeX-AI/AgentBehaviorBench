"""Compatibility router for the old standalone AI server."""

from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.core.security import require_internal_ai_token
from app.modules.ai.service import analysis

router = APIRouter()


@router.post("/api/chat/image/analysis", response_class=PlainTextResponse)
async def image_analysis(
    payload: Any,
    _: None = Depends(require_internal_ai_token),
) -> PlainTextResponse:
    """Keep `/api/chat/image/analysis` returning raw model text like Java did."""

    return PlainTextResponse(await analysis(payload))
