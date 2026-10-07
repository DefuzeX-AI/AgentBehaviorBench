"""Server-Sent Events endpoints compatible with the Java demo controller."""

import asyncio
import json
import time
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.responses import json_success

router = APIRouter()
_emitters: list[asyncio.Queue[str]] = []


def _event(name: str, data: dict[str, Any]) -> str:
    """Format one SSE event frame."""

    return f"id: {int(time.time() * 1000)}\nevent: {name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


@router.get("/api/sse")
async def connect(request: Request):
    """Open an SSE stream and register it for later broadcasts."""

    queue: asyncio.Queue[str] = asyncio.Queue()
    _emitters.append(queue)
    await queue.put(_event("connect", {"message": "\u8fde\u63a5\u6210\u529f\uff01"}))

    async def stream():
        """Yield queued events and keep-alives until the client disconnects."""

        try:
            while not await request.is_disconnected():
                try:
                    yield await asyncio.wait_for(queue.get(), timeout=15)
                except asyncio.TimeoutError:
                    yield ": keep-alive\n\n"
        finally:
            if queue in _emitters:
                _emitters.remove(queue)

    return StreamingResponse(stream(), media_type="text/event-stream")


@router.post("/api/sse")
async def send_message(payload: dict[str, Any]):
    """Broadcast a message payload to all active SSE streams."""

    message = payload.get("message")
    dead: list[asyncio.Queue[str]] = []
    for queue in list(_emitters):
        try:
            queue.put_nowait(_event("message", {"message": message}))
        except Exception:
            dead.append(queue)
    for queue in dead:
        if queue in _emitters:
            _emitters.remove(queue)
    return json_success('{"status": "success", "message": "\u6d88\u606f\u5df2\u53d1\u9001"}')
