"""WebSocket engine bridge via RealtimeManager RPC."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.modules.envs.engine_bridge import register_bridge
from app.modules.envs.interaction import InteractionConfig, build_observation_query
from app.modules.envs.scenario import ScenarioSpec

logger = logging.getLogger(__name__)

# Top-level keys that hold per-agent command dicts (multi-agent env actions).
_AGENT_CONTAINER_KEYS = ("drones", "agents", "fleet")

_FAILED_ACK_STATUSES = frozenset(
    {"error", "failed", "timeout", "dispatched_without_ack", "rejected"}
)


def agent_container_key(action: dict[str, Any]) -> str | None:
    """Return the first multi-agent container key present in *action*."""

    for key in _AGENT_CONTAINER_KEYS:
        value = action.get(key)
        if isinstance(value, dict) and value:
            return key
    return None


def split_action_for_batched_mode(action: dict[str, Any]) -> list[dict[str, Any]]:
    """Split a multi-agent action into one payload per agent for ``dispatch_mode=batched``."""

    container = agent_container_key(action)
    if container is None:
        return [action]

    task_id = action.get("task_id") or action.get("taskId")
    batches: list[dict[str, Any]] = []
    for agent_name, agent_cmd in action[container].items():
        payload: dict[str, Any] = {container: {agent_name: agent_cmd}, "agent": agent_name}
        if task_id:
            payload["task_id"] = task_id
            payload["taskId"] = task_id
        batches.append(payload)
    return batches


@register_bridge("realtime")
class RealtimeEngineBridge:
    """Push scenario init + actions to LJ-ENGINE through the existing WebSocket layer.

    The bridge does two things on top of the raw WS RPC:

    1. Stamp every outbound payload with the episode ``task_id`` so the engine
       can route replies and our SQLite layer can group ``sim_data`` rows.
    2. On reset, ship the engine-compatible \u60f3\u5b9a JSON (sceneName / equipmentList /
       taskMatrix) verbatim, matching the production message shape.

    ``InteractionConfig.action`` fields consumed here:

    * ``dispatch_mode`` \u2014 ``broadcast`` | ``unicast`` | ``batched``
    * ``require_ack`` \u2014 RPC wait vs fire-and-forget
    * ``timeout_sec`` \u2014 RPC timeout per attempt
    * ``retry`` \u2014 re-attempt the whole dispatch on failure (0 = no retry)
    * ``extra.engine_session_key`` \u2014 force a ``userType_userAddress`` session key
    """

    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]:
        from app.modules.realtime.manager import realtime_manager

        payload = spec.to_engine_payload()
        message = {
            "commandType": "resetScenario",
            "taskId": spec.task_id,
            "scenario": payload,
        }
        try:
            response = await realtime_manager.request_to_engine(
                message, timeout=cfg.observation.timeout_sec
            )
        except Exception:
            await realtime_manager.send_by_user_type(
                {"type": "COMMAND", "data": message}, "LJ-ENGINE"
            )
            response = {"status": "dispatched_without_ack"}
        realtime_manager.persist_task_data(
            spec.task_id, {"phase": "reset", "scenario": payload, "response": response}
        )
        return response

    async def request_observation(self, query: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        from app.modules.realtime.manager import realtime_manager

        cmd = cfg.engine_commands.request_observation
        enriched_query = build_observation_query(query, cfg)
        task_id = enriched_query.get("task_id") or enriched_query.get("taskId") or ""
        return await realtime_manager.request_to_engine(
            {"commandType": cmd, "taskId": task_id, "query": enriched_query},
            timeout=cfg.observation.timeout_sec,
        )

    @staticmethod
    def _resolve_session_key(action: dict[str, Any], cfg: InteractionConfig) -> str | None:
        key = cfg.action.extra.get("engine_session_key") or action.get("engine_session_key")
        if key:
            return str(key)
        legacy = action.get("engineSessionKey")
        return str(legacy) if legacy else None

    @staticmethod
    def _target_dispatch_mode(cfg: InteractionConfig) -> str:
        """Map ``batched`` to unicast target selection (one engine, many messages)."""

        mode = cfg.action.dispatch_mode
        if mode == "batched":
            return "unicast"
        return mode

    @staticmethod
    def _ack_successful(ack: dict[str, Any], *, require_ack: bool) -> bool:
        if not require_ack:
            return True
        status = str(ack.get("status", "")).lower()
        if status in _FAILED_ACK_STATUSES:
            return False
        return not ack.get("error")

    async def _dispatch_once(
        self,
        action: dict[str, Any],
        cfg: InteractionConfig,
    ) -> dict[str, Any]:
        from app.modules.realtime.manager import realtime_manager

        cmd = cfg.engine_commands.execute_action
        task_id = action.get("task_id") or action.get("taskId") or ""
        session_key = self._resolve_session_key(action, cfg)
        targets = realtime_manager.resolve_lj_engine_targets(
            dispatch_mode=self._target_dispatch_mode(cfg),
            task_id=task_id or None,
            session_key=session_key,
        )
        if not targets:
            raise RuntimeError("LJ-ENGINE \u672a\u8fde\u63a5\uff0c\u65e0\u6cd5\u4e0b\u53d1\u52a8\u4f5c")

        mode = cfg.action.dispatch_mode
        payloads = (
            split_action_for_batched_mode(action) if mode == "batched" else [action]
        )
        message_base = {"commandType": cmd, "taskId": task_id}
        require_ack = cfg.action.require_ack
        batch_acks: list[dict[str, Any]] = []

        for index, payload in enumerate(payloads):
            message = {**message_base, "action": payload}
            if require_ack:
                ack = await realtime_manager.request_to_engine(
                    message,
                    timeout=cfg.action.timeout_sec,
                    targets=targets,
                )
                batch_acks.append(ack)
                if not self._ack_successful(ack, require_ack=True):
                    return {
                        "status": "failed",
                        "batch_index": index,
                        "batch_total": len(payloads),
                        "acks": batch_acks,
                        "dispatch_mode": mode,
                    }
            else:
                await realtime_manager.send_command_to_engine(message, targets=targets)
                batch_acks.append({"status": "sent", "agent": payload.get("agent")})

        if mode == "batched":
            return {
                "status": "ok" if require_ack else "sent",
                "batched": True,
                "batch_count": len(payloads),
                "acks": batch_acks,
                "dispatch_mode": mode,
                "target_count": len(targets),
            }
        return batch_acks[0] if batch_acks else {"status": "sent"}

    async def dispatch_action(self, action: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        from app.modules.realtime.manager import realtime_manager

        task_id = action.get("task_id") or action.get("taskId") or ""
        max_attempts = 1 + max(0, int(cfg.action.retry))
        last_ack: dict[str, Any] = {"status": "failed", "error": "no attempt made"}
        last_error: Exception | None = None

        for attempt in range(max_attempts):
            try:
                last_ack = await self._dispatch_once(action, cfg)
                if self._ack_successful(last_ack, require_ack=cfg.action.require_ack):
                    last_ack.setdefault("attempt", attempt + 1)
                    last_ack.setdefault("dispatch_mode", cfg.action.dispatch_mode)
                    realtime_manager.persist_task_data(
                        task_id,
                        {
                            "phase": "action",
                            "action": action,
                            "ack": last_ack,
                            "attempt": attempt + 1,
                        },
                    )
                    return last_ack
                logger.warning(
                    "dispatch_action attempt %s/%s returned non-success ack: %s",
                    attempt + 1,
                    max_attempts,
                    last_ack,
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                last_ack = {"status": "error", "error": str(exc)}
                logger.warning(
                    "dispatch_action attempt %s/%s raised: %s",
                    attempt + 1,
                    max_attempts,
                    exc,
                )

            if attempt < max_attempts - 1:
                await asyncio.sleep(min(0.5, 0.1 * (attempt + 1)))

        last_ack.setdefault("attempts", max_attempts)
        last_ack.setdefault("dispatch_mode", cfg.action.dispatch_mode)
        if last_error and "error" not in last_ack:
            last_ack["error"] = str(last_error)
        realtime_manager.persist_task_data(
            task_id,
            {"phase": "action", "action": action, "ack": last_ack, "failed": True},
        )
        if last_error and max_attempts == 1:
            raise last_error
        return last_ack

    async def call_custom(self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        from app.modules.realtime.manager import realtime_manager

        cmd = cfg.engine_commands.custom.get(command_name, command_name)
        return await realtime_manager.request_to_engine(
            {"commandType": cmd, "payload": payload},
            timeout=cfg.action.timeout_sec,
        )

    async def close(self) -> None:
        return None
