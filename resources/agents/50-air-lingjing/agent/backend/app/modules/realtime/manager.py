"""In-process WebSocket session manager matching the Java connection maps."""

import asyncio
import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import Any

from fastapi import WebSocket

from app.core.logging import format_ws_payload
from app.core.responses import AppError

logger = logging.getLogger(__name__)

from app.db.models import SimData
from app.db.session import StreamSessionLocal


class RealtimeManager:
    """Track WebSocket sessions by user type, session key, and task subscription."""

    def __init__(self) -> None:
        # These maps mirror Java's sessionMap, sceneSessionMap, and SESSION_CONCURRENT_MAP.
        self.session_map: dict[str, dict[str, WebSocket]] = {
            "LJ-UE": {},
            "LJ-ENGINE": {},
            "LJ-CREW": {},
        }
        self.scene_session_map: dict[str, dict[str, WebSocket]] = defaultdict(dict)
        self.session_key_map: dict[str, WebSocket] = {}
        self._pending: dict[str, asyncio.Future] = {}
        self._event_waiters: list[dict[str, Any]] = []
        
        
        
        
        
        
        self._recent_events: list[dict[str, Any]] = []  # [{"ts","session_key","command_type","payload"}]
        self._requested_command_types: set[str] = set()
        self._event_buffer_ttl_sec: float = 90.0
        self._event_buffer_max: int = 100

    def _log_ws(
        self,
        direction: str,
        session_key: str,
        payload: Any,
        *,
        note: str = "",
    ) -> None:
        """Write one WebSocket traffic line to logs/websocket.log."""

        if not logger.isEnabledFor(logging.INFO):
            return
        parts = [direction, f"session={session_key}"]
        if note:
            parts.append(note)
        parts.append(f"body={format_ws_payload(payload)}")
        logger.info(" ".join(parts))

    @staticmethod
    def session_key(user_type: str, user_address: str) -> str:
        """Build the `userType_userAddress` key used by the Java service."""

        return f"{user_type}_{user_address}"

    async def connect(self, websocket: WebSocket, user_type: str, user_address: str) -> str:
        """Accept a WebSocket and register it in all relevant lookup maps."""

        if user_type not in self.session_map:
            await websocket.close(code=1008)
            raise ValueError("\u7528\u6237\u7c7b\u578b\u4e0d\u652f\u6301")
        await websocket.accept()
        key = self.session_key(user_type, user_address)
        old = self.session_key_map.get(key)
        if old is not None:
            self._log_ws("EVENT", key, {"event": "replace_session", "reason": "duplicate_connect"})
            try:
                await old.send_json({"type": "SYSTEM", "data": "\u5f53\u524dIP\u91cd\u590d\u8fde\u63a5\uff0c\u5f53\u524d\u4f1a\u8bdd\u5373\u5c06\u5173\u95ed!"})
                await old.close()
            except Exception:
                pass
        self.session_map[user_type][key] = websocket
        self.session_key_map[key] = websocket
        await websocket.send_json({"type": "SYSTEM", "data": {"code": 0, "message": f"Hello,{user_address}"}})
        self._log_ws(
            "OUT",
            key,
            {"type": "SYSTEM", "data": {"code": 0, "message": f"Hello,{user_address}"}},
            note=f"event=connect user_type={user_type}",
        )
        return key

    def disconnect(self, key: str, websocket: WebSocket | None = None) -> None:
        """Remove a session from every in-memory registry."""

        current = self.session_key_map.get(key)
        if websocket is not None and current is not None and current is not websocket:
            self._log_ws("EVENT", key, {"event": "disconnect_ignored", "reason": "stale_socket"})
            return

        self._log_ws("EVENT", key, {"event": "disconnect"})

        self.session_key_map.pop(key, None)
        for sessions in self.session_map.values():
            if websocket is None or sessions.get(key) is websocket:
                sessions.pop(key, None)
        for sessions in self.scene_session_map.values():
            if websocket is None or sessions.get(key) is websocket:
                sessions.pop(key, None)

    @staticmethod
    def _extract_request_id(message: dict[str, Any]) -> str | None:
        """Read correlation id from either snake_case or camelCase field."""

        request_id = message.get("request_id") or message.get("requestId")
        if request_id is None:
            return None
        return str(request_id)

    def _try_resolve_rpc(self, socket_message: dict[str, Any]) -> bool:
        """Resolve a pending RPC future when the inbound message carries a matching id.

        Any ``commandType`` is accepted \u2014 e.g. ``fireRescueActionAck`` or custom engine
        ack names \u2014 as long as ``request_id`` / ``requestId`` matches a pending future.
        """

        request_id = self._extract_request_id(socket_message)
        if not request_id or request_id not in self._pending:
            return False
        future = self._pending.pop(request_id)
        if not future.done():
            payload = (
                socket_message.get("data")
                or socket_message.get("payload")
                or socket_message
            )
            future.set_result(payload)
        return True

    @staticmethod
    def _event_payload(socket_message: dict[str, Any]) -> dict[str, Any]:
        payload = socket_message.get("data") or socket_message.get("payload")
        if isinstance(payload, dict) and payload.get("commandType"):
            return payload
        return socket_message

    @staticmethod
    def _event_drone_id(payload: dict[str, Any]) -> str | None:
        
        
        value = (
            payload.get("droneID")
            or payload.get("droneId")
            or payload.get("dronesId")
            or payload.get("uavId")
            or payload.get("dogID")
            or payload.get("dogId")
            or payload.get("unmannedDogId")
            or payload.get("carID")
            or payload.get("carId")
            or payload.get("autocarId")
        )
        return str(value) if value is not None else None

    def _event_matches(self, *, ev_command_type: str, ev_payload: dict[str, Any],
                       ev_session_key: str | None, want_command_types: set[str],
                       filters: dict[str, Any], waiter_session_key: str | None) -> bool:
        """\u4e8b\u4ef6\u662f\u5426\u6ee1\u8db3\u67d0\u4e2a\u7b49\u5f85\u8005\u7684\u6761\u4ef6 (commandType + session + droneId/dogId/carId + taskId)\u3002

        \u5b9e\u65f6\u5339\u914d (_try_resolve_engine_event) \u4e0e\u7f13\u5b58\u56de\u653e (_take_recent_event) \u5171\u7528\u6b64\u903b\u8f91, \u907f\u514d\u5206\u53c9\u3002
        \u6ce8\u610f taskId: \u5f15\u64ce\u90e8\u5206\u56de\u6267 taskId \u4e3a\u7a7a\u4e32 (\u5982\u65e0\u4eba\u72d7), \u6b64\u65f6\u89c6\u4e3a"\u672a\u643a\u5e26"\u2192 \u4e0d\u53c2\u4e0e\u8fc7\u6ee4 (\u4e0d\u62e6\u622a)\u3002
        """

        if waiter_session_key and waiter_session_key != ev_session_key:
            return False
        if ev_command_type not in want_command_types:
            return False
        expected_drone_id = filters.get("droneId") or filters.get("droneID")
        if expected_drone_id is not None and self._event_drone_id(ev_payload) != str(expected_drone_id):
            return False
        expected_task_id = filters.get("taskId") or filters.get("task_id")
        actual_task_id = ev_payload.get("taskId") or ev_payload.get("task_id")
        if expected_task_id is not None and actual_task_id:  
            if str(actual_task_id) != str(expected_task_id):
                return False
        return True

    def _try_resolve_engine_event(self, session_key: str, socket_message: dict[str, Any]) -> bool:
        payload = self._event_payload(socket_message)
        command_type = payload.get("commandType")
        
        
        if not command_type and isinstance(payload, dict) and payload.get("isReady") is not None:
            command_type = "isReady"
        if not command_type:
            return False

        resolved = False
        for waiter in list(self._event_waiters):
            future = waiter["future"]
            if future.done():
                self._event_waiters.remove(waiter)
                continue
            expected_command_types = waiter.get("command_types") or {waiter.get("command_type")}
            if not self._event_matches(
                ev_command_type=command_type, ev_payload=payload, ev_session_key=session_key,
                want_command_types=expected_command_types, filters=waiter.get("filters") or {},
                waiter_session_key=waiter.get("session_key"),
            ):
                continue
            self._event_waiters.remove(waiter)
            future.set_result(payload)
            resolved = True

        
        
        if not resolved and command_type in self._requested_command_types:
            now = time.monotonic()
            self._recent_events = [
                r for r in self._recent_events if now - r["ts"] <= self._event_buffer_ttl_sec
            ][-(self._event_buffer_max - 1):]
            self._recent_events.append({
                "ts": now, "session_key": session_key,
                "command_type": command_type, "payload": payload,
            })
        return resolved

    def _take_recent_event(
        self, command_types: set[str], filters: dict[str, Any], session_key: str | None
    ) -> dict[str, Any] | None:
        """\u53d6\u4e00\u6761\u4ecd\u5728 TTL \u5185\u3001\u4e14\u6ee1\u8db3\u7b49\u5f85\u6761\u4ef6\u7684\u5df2\u7f13\u5b58\u4e8b\u4ef6 (\u53d6\u8d70\u5373\u6d88\u8d39, \u7535\u5e73\u89e6\u53d1)\u3002"""

        now = time.monotonic()
        fresh = [r for r in self._recent_events if now - r["ts"] <= self._event_buffer_ttl_sec]
        for idx, rec in enumerate(fresh):
            if self._event_matches(
                ev_command_type=rec["command_type"], ev_payload=rec["payload"],
                ev_session_key=rec["session_key"], want_command_types=command_types,
                filters=filters or {}, waiter_session_key=session_key,
            ):
                self._recent_events = fresh[:idx] + fresh[idx + 1 :]
                return rec["payload"]
        self._recent_events = fresh
        return None
        self._recent_ready = fresh
        return None

    async def handle_message(self, key: str, raw_message: str) -> None:
        """Route incoming WebSocket messages by legacy ``commandType``.

        RPC replies are detected first: any inbound message whose ``request_id`` /
        ``requestId`` matches a pending :meth:`request_to_engine` call completes that
        future, regardless of ``commandType``.
        """

        socket_message = json.loads(raw_message)
        command_type = socket_message.get("commandType")
        request_id = self._extract_request_id(socket_message)
        rpc_note = ""
        if request_id and request_id in self._pending:
            rpc_note = f" event=rpc_reply request_id={request_id}"
        elif command_type:
            rpc_note = f" commandType={command_type}"
        self._log_ws("IN", key, socket_message, note=f"event=receive_json{rpc_note}")
        if self._try_resolve_rpc(socket_message):
            return
        if self._try_resolve_engine_event(key, socket_message):
            return

        command_type = socket_message.get("commandType")
        if command_type == "pushEngineTelemetry":
            # UE (LJ-ENGINE) proactively pushes high-frequency sim frames; persist by taskId.
            task_id = str(
                socket_message.get("taskId")
                or socket_message.get("task_id")
                or (socket_message.get("data") or {}).get("taskId")
                or ""
            )
            telemetry = (
                socket_message.get("data")
                or socket_message.get("telemetry")
                or socket_message
            )
            self.persist_task_data(
                task_id,
                {"phase": "telemetry", "source": key, "telemetry": telemetry},
            )
            return
        if command_type == "subscribeScene":
            task_id = str((socket_message.get("command") or {}).get("taskId"))
            self.scene_session_map[task_id][key] = self.session_key_map[key]
            return
        if command_type == "unsubscribeScene":
            task_id = str((socket_message.get("command") or {}).get("taskId"))
            self.scene_session_map.get(task_id, {}).pop(key, None)
            return
        if command_type == "sendToUE":
            command_array = socket_message.get("commandArray")
            command = socket_message.get("command")
            data = command_array if command_array is not None else [command]
            await self.send_by_user_type({"type": "DATA", "data": data}, "LJ-UE")
            self._save_scene_data(socket_message)
            return
        if command_type == "sendToEngine":
            await self.send_by_user_type({"type": "DATA", "data": socket_message.get("command")}, "LJ-ENGINE")
            return
        if command_type == "sendCommandToUE":
            data = socket_message.get("commandArray")
            if data is None:
                data = socket_message.get("command")
            await self.send_by_user_type({"type": "COMMAND", "data": data}, "LJ-UE")
            return
        receiver = socket_message.get("receiver")
        await self.send_by_user_type({"type": "COMMAND", "data": socket_message.get("command")}, receiver)

    def persist_task_data(self, task_id: str | None, data: Any) -> None:
        """Append a row in ``sim_data`` tagged with the closed-loop task id."""

        if not task_id:
            return
        try:
            with StreamSessionLocal() as db:
                row = SimData(
                    task_id=str(task_id),
                    data=json.dumps(data, ensure_ascii=False, default=str),
                    create_time=datetime.now(),
                    update_time=datetime.now(),
                )
                db.add(row)
                db.commit()
        except Exception:  # noqa: BLE001
            logger.exception("Failed to persist task data for task_id=%s", task_id)

    def resolve_lj_engine_targets(
        self,
        *,
        dispatch_mode: str = "broadcast",
        task_id: str | None = None,
        session_key: str | None = None,
    ) -> list[WebSocket]:
        """Pick WebSocket session(s) for outbound engine commands.

        * ``broadcast`` \u2014 every connected ``LJ-ENGINE`` session.
        * ``unicast`` / ``batched`` \u2014 a single engine: explicit ``session_key``,
          else first ``subscribeScene`` subscriber for ``task_id``, else the first
          connected ``LJ-ENGINE`` socket.
        """

        if session_key:
            websocket = self.session_key_map.get(session_key)
            return [websocket] if websocket is not None else []

        engine_sessions = self.session_map.get("LJ-ENGINE", {})
        if dispatch_mode == "broadcast":
            return list(engine_sessions.values())

        if task_id:
            subscribed = self.scene_session_map.get(str(task_id), {})
            for key, websocket in subscribed.items():
                if key in engine_sessions:
                    return [websocket]

        if engine_sessions:
            return [next(iter(engine_sessions.values()))]
        return []

    async def request_to_engine(
        self,
        command: dict[str, Any],
        timeout: float = 5.0,
        *,
        targets: list[WebSocket] | None = None,
    ) -> dict[str, Any]:
        """Send a request to LJ-ENGINE and wait for a correlated response."""

        request_id = str(uuid.uuid4())
        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        self._pending[request_id] = future
        outbound = {**command, "request_id": request_id, "requestId": request_id}
        sessions = targets if targets is not None else list(self.session_map.get("LJ-ENGINE", {}).values())
        if not sessions:
            self._pending.pop(request_id, None)
            self._log_ws(
                "ERROR",
                "rpc",
                outbound,
                note=f"event=rpc_send_failed request_id={request_id} reason=no_engine_connected",
            )
            raise AppError("LJ-ENGINE \u672a\u8fde\u63a5\uff0c\u65e0\u6cd5\u8bf7\u6c42\u73af\u5883\u89c2\u6d4b")
        await self._send_many(
            sessions,
            {"type": "COMMAND", "data": outbound},
            note=(
                f"event=rpc_send request_id={request_id} "
                f"commandType={command.get('commandType')}"
            ),
        )
        try:
            result = await asyncio.wait_for(future, timeout=timeout)
            return dict(result) if isinstance(result, dict) else {"data": result}
        except asyncio.TimeoutError as exc:
            self._pending.pop(request_id, None)
            self._log_ws(
                "ERROR",
                "rpc",
                outbound,
                note=f"event=rpc_timeout request_id={request_id} timeout={timeout}s",
            )
            raise AppError(f"\u5f15\u64ce\u54cd\u5e94\u8d85\u65f6 ({timeout}s)") from exc

    async def wait_for_engine_event(
        self,
        command_type: str | list[str],
        *,
        filters: dict[str, Any] | None = None,
        session_key: str | None = None,
        timeout: float | None = 30.0,
    ) -> dict[str, Any]:
        """Wait for a future inbound LJ-ENGINE event without requestId correlation."""

        loop = asyncio.get_running_loop()
        future: asyncio.Future = loop.create_future()
        if isinstance(command_type, (list, tuple, set)):
            command_types = {str(item) for item in command_type if str(item).strip()}
        else:
            command_types = {str(command_type)}
        
        self._requested_command_types.update(command_types)
        
        
        cached = self._take_recent_event(command_types, filters or {}, session_key)
        if cached is not None:
            return dict(cached) if isinstance(cached, dict) else {"data": cached}

        waiter = {
            "command_type": next(iter(command_types)) if command_types else "",
            "command_types": command_types,
            "filters": filters or {},
            "session_key": session_key,
            "future": future,
        }
        self._event_waiters.append(waiter)
        try:
            if timeout is None or timeout <= 0:
                result = await future
            else:
                result = await asyncio.wait_for(future, timeout=timeout)
            return dict(result) if isinstance(result, dict) else {"data": result}
        except asyncio.TimeoutError as exc:
            if waiter in self._event_waiters:
                self._event_waiters.remove(waiter)
            raise AppError(f"\u7b49\u5f85\u5f15\u64ce\u4e8b\u4ef6 {command_type} \u8d85\u65f6 ({timeout}s)") from exc

    async def send_command_to_engine(
        self,
        data: dict[str, Any],
        *,
        targets: list[WebSocket] | None = None,
    ) -> None:
        """Fire-and-forget COMMAND envelope to selected LJ-ENGINE session(s)."""

        sessions = targets if targets is not None else list(self.session_map.get("LJ-ENGINE", {}).values())
        if not sessions:
            self._log_ws(
                "ERROR",
                "engine",
                data,
                note="event=command_send_failed reason=no_engine_connected",
            )
            raise AppError("LJ-ENGINE \u672a\u8fde\u63a5\uff0c\u65e0\u6cd5\u4e0b\u53d1\u6307\u4ee4")
        await self._send_many(
            sessions,
            {"type": "COMMAND", "data": data},
            note=(
                f"event=command_send commandType={data.get('commandType')} "
                f"fire_and_forget=true"
            ),
        )

    async def send_by_user_type(self, message: dict[str, Any], user_type: str | None) -> None:
        """Broadcast a message to all sessions under a Java user type."""

        if not user_type:
            return
        await self._send_many(
            self.session_map.get(user_type, {}).values(),
            message,
            note=f"event=broadcast_user_type user_type={user_type}",
        )

    async def send_by_task_id(self, message: dict[str, Any], task_id: str | None) -> None:
        """Broadcast a message to sessions subscribed to a task id."""

        if not task_id:
            return
        await self._send_many(
            self.scene_session_map.get(str(task_id), {}).values(),
            message,
            note=f"event=broadcast_task task_id={task_id}",
        )

    async def send_by_address(self, message: dict[str, Any], session_key: str) -> None:
        """Send a message to a single `userType_userAddress` session key."""

        websocket = self.session_key_map.get(session_key)
        if websocket:
            self._log_ws("OUT", session_key, message, note="event=send_by_address")
            await websocket.send_json(message)

    async def close_session(self, session_key: str) -> bool:
        """Close a session from the management API."""

        websocket = self.session_key_map.get(session_key)
        if websocket is None:
            return False
        await websocket.close()
        self.disconnect(session_key)
        return True

    async def _send_many(
        self,
        websockets,
        message: dict[str, Any],
        *,
        log_payload: bool = True,
        note: str = "",
    ) -> None:
        """Send JSON to many sockets and clear sessions that fail writes."""

        closed: list[str] = []
        for key, websocket in list(self.session_key_map.items()):
            if websocket not in websockets:
                continue
            if log_payload:
                self._log_ws("OUT", key, message, note=note or "event=send_json")
            try:
                await websocket.send_json(message)
            except Exception as exc:
                self._log_ws(
                    "ERROR",
                    key,
                    message,
                    note=f"event=send_failed error={exc}",
                )
                closed.append(key)
        for key in closed:
            self.disconnect(key)

    def get_sessions_info(self) -> dict[str, Any]:
        """Return session metadata compatible with `/websocket/api/sessions`."""

        sessions_by_type: dict[str, list[dict[str, Any]]] = {}
        for user_type, sessions in self.session_map.items():
            sessions_by_type[user_type] = [
                {"sessionKey": key, "isOpen": True, "id": key, "connected": True}
                for key in sessions.keys()
            ]
        return {
            "sessionsByType": sessions_by_type,
            "totalCount": len(self.session_key_map),
            "sceneSubscriptions": len(self.scene_session_map),
        }

    def _save_scene_data(self, socket_message: dict[str, Any]) -> None:
        """Persist `sendToUE` simulation data for replay/query endpoints."""

        data = socket_message.get("command")
        if data is None:
            data = socket_message.get("commandArray")
        with StreamSessionLocal() as db:
            sim_data = SimData(
                task_id=socket_message.get("taskId"),
                data=json.dumps(data, ensure_ascii=False),
            )
            db.add(sim_data)
            db.commit()


realtime_manager = RealtimeManager()
