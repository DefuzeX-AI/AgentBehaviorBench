"""WebSocket endpoint and management APIs."""

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse

from app.core.responses import json_success
from app.modules.realtime.manager import realtime_manager

router = APIRouter()


@router.websocket("/ws/{userType}/{userAddress}")
async def websocket_endpoint(websocket: WebSocket, userType: str, userAddress: str):
    """Keep the original `/ws/{userType}/{userAddress}` realtime contract."""

    key = await realtime_manager.connect(websocket, userType, userAddress)
    try:
        while True:
            message = await websocket.receive_text()
            await realtime_manager.handle_message(key, message)
    except WebSocketDisconnect:
        realtime_manager.disconnect(key, websocket)


@router.get("/websocket/page", response_class=HTMLResponse)
def websocket_page():
    """Small replacement for the Java websocket management HTML page."""

    return HTMLResponse(
        """
        <!doctype html>
        <html><head><meta charset="utf-8"><title>WebSocket Manage</title></head>
        <body><h1>WebSocket \u7ba1\u7406</h1><p>Use /websocket/api/sessions for session data.</p></body>
        </html>
        """
    )


@router.get("/websocket/api/sessions")
def get_sessions():
    """Return active WebSocket sessions grouped by user type."""

    return json_success(realtime_manager.get_sessions_info())


@router.post("/websocket/api/close/{sessionKey}")
async def close_session(sessionKey: str):
    """Close one active WebSocket session by its legacy session key."""

    closed = await realtime_manager.close_session(sessionKey)
    if not closed:
        raise RuntimeError("\u4f1a\u8bdd\u4e0d\u5b58\u5728")
    return json_success("\u5173\u95ed\u6210\u529f")
