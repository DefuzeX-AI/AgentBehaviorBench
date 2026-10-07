"""Dispatch entity-control commands to LJ-ENGINE WebSocket sessions."""

from __future__ import annotations

from typing import Any

from app.modules.realtime.manager import realtime_manager

_ROUTING_KEYS = {
    "engineAddress",
    "engine_address",
    "engineSessionKey",
    "engine_session_key",
    "broadcast",
    "dryRun",
    "dry_run",
    "requireAck",
    "require_ack",
    "timeoutSec",
    "timeout_sec",
    "command",
    "scenario",
}


def _bool_from_payload(payload: dict[str, Any], *keys: str, default: bool = False) -> bool:
    for key in keys:
        if key not in payload:
            continue
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        return bool(value)
    return default


def _float_from_payload(payload: dict[str, Any], *keys: str, default: float | None = None) -> float | None:
    for key in keys:
        if payload.get(key) is not None:
            return float(payload[key])
    return default


def _int_or_raw(value: Any) -> Any:
    if isinstance(value, str) and value.strip().isdigit():
        return int(value)
    return value


def _task_id(payload: dict[str, Any]) -> str:
    task_id = payload.get("taskId") or payload.get("task_id")
    if not task_id:
        raise ValueError("taskId \u4e0d\u80fd\u4e3a\u7a7a")
    return str(task_id)


def _non_empty_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _photo_entity_id(item: dict[str, Any]) -> str:
    upload_spec = item.get("uploadSpec") if isinstance(item.get("uploadSpec"), dict) else {}
    fields = upload_spec.get("fields") if isinstance(upload_spec.get("fields"), dict) else {}
    for key in (
        "agentId",
        "droneId",
        "dogId",
        "carId",
        "autocarId",
        "modelId",
        "name",
    ):
        value = _non_empty_text(item.get(key)) or _non_empty_text(fields.get(key))
        if value:
            return value
    return "unknown_entity"


def _with_photo_id(task_id: str, item: Any) -> Any:
    if not isinstance(item, dict):
        return item
    normalized = dict(item)
    upload_spec = normalized.get("uploadSpec")
    fields: dict[str, Any] | None = None
    if isinstance(upload_spec, dict):
        upload_spec = dict(upload_spec)
        raw_fields = upload_spec.get("fields")
        if isinstance(raw_fields, dict):
            fields = dict(raw_fields)

    entity_id = _photo_entity_id(normalized)
    view_type = (
        _non_empty_text(normalized.get("viewType"))
        or _non_empty_text(fields.get("viewType") if fields is not None else None)
        or "unknown_view"
    )
    step_index = (
        _non_empty_text(normalized.get("stepIndex"))
        or _non_empty_text(fields.get("stepIndex") if fields is not None else None)
        or "0"
    )
    photo_id = (
        _non_empty_text(normalized.get("photoid"))
        or _non_empty_text(fields.get("photoid") if fields is not None else None)
        or f"{task_id}_{entity_id}_{view_type}_step_{step_index}"
    )
    normalized["photoid"] = photo_id
    if fields is not None and upload_spec is not None:
        fields["photoid"] = photo_id
        upload_spec["fields"] = fields
        normalized["uploadSpec"] = upload_spec
    return normalized


def _engine_session_key(payload: dict[str, Any], default_engine_address: str | None) -> str | None:
    explicit = payload.get("engineSessionKey") or payload.get("engine_session_key")
    if explicit:
        return str(explicit)
    address = payload.get("engineAddress") or payload.get("engine_address") or default_engine_address
    if address:
        text = str(address)
        return text if text.startswith("LJ-ENGINE_") else f"LJ-ENGINE_{text}"
    return None


def _connected_engine_targets(engine_session_key: str | None = None) -> tuple[list[str], list[Any]]:
    sessions = realtime_manager.session_map.get("LJ-ENGINE", {})
    if engine_session_key:
        websocket = realtime_manager.session_key_map.get(engine_session_key)
        return ([engine_session_key], [websocket]) if websocket is not None else ([], [])
    return list(sessions.keys()), list(sessions.values())


def _route_options(
    payload: dict[str, Any],
    *,
    default_engine_address: str | None,
    default_require_ack: bool = False,
) -> tuple[str | None, bool, bool, bool, float]:
    session_key = _engine_session_key(payload, default_engine_address)
    broadcast = _bool_from_payload(payload, "broadcast", default=session_key is None)
    dry_run = _bool_from_payload(payload, "dryRun", "dry_run", default=False)
    require_ack = _bool_from_payload(
        payload, "requireAck", "require_ack", default=default_require_ack
    )
    timeout_sec = _float_from_payload(payload, "timeoutSec", "timeout_sec", default=5.0)
    return session_key, broadcast, dry_run, require_ack, float(timeout_sec or 5.0)


async def dispatch_engine_command(
    payload: dict[str, Any],
    command: dict[str, Any],
    *,
    default_engine_address: str | None,
    default_require_ack: bool = False,
) -> dict[str, Any]:
    session_key, broadcast, dry_run, require_ack, timeout_sec = _route_options(
        payload,
        default_engine_address=default_engine_address,
        default_require_ack=default_require_ack,
    )
    if session_key and not broadcast:
        target_keys, targets = _connected_engine_targets(session_key)
    elif session_key and broadcast:
        target_keys, targets = _connected_engine_targets(session_key)
    else:
        target_keys, targets = _connected_engine_targets()

    result: dict[str, Any] = {
        "taskId": command.get("taskId"),
        "commandType": command.get("commandType"),
        "targets": target_keys,
        "targetCount": len(targets),
        "requiresAck": require_ack,
        "dryRun": dry_run,
        "command": command,
    }
    if dry_run:
        result["status"] = "dry_run"
        return result
    if not targets:
        raise RuntimeError("LJ-ENGINE \u672a\u8fde\u63a5\uff0c\u65e0\u6cd5\u4e0b\u53d1\u6307\u4ee4")

    if require_ack:
        result["response"] = await realtime_manager.request_to_engine(
            command,
            timeout=timeout_sec,
            targets=targets,
        )
    else:
        await realtime_manager.send_command_to_engine(command, targets=targets)
        result["response"] = {"status": "sent"}
    result["status"] = "sent"
    return result


async def wait_engine_event(payload: dict[str, Any]) -> dict[str, Any]:
    raw_command_types = payload.get("commandTypes") or payload.get("command_types")
    if isinstance(raw_command_types, list):
        command_types = [str(item).strip() for item in raw_command_types if str(item).strip()]
    else:
        command_type = str(payload.get("commandType") or payload.get("command_type") or "").strip()
        command_types = [command_type] if command_type else []
    if not command_types:
        raise ValueError("commandType \u4e0d\u80fd\u4e3a\u7a7a")
    session_key = _engine_session_key(payload, None)
    timeout_sec = _float_from_payload(payload, "timeoutSec", "timeout_sec", default=30.0)
    filters = payload.get("filters")
    if not isinstance(filters, dict):
        filters = {}
    if payload.get("taskId") or payload.get("task_id"):
        filters = {**filters, "taskId": _task_id(payload)}
    response = await realtime_manager.wait_for_engine_event(
        command_types if len(command_types) > 1 else command_types[0],
        filters=filters,
        session_key=session_key,
        timeout=None if timeout_sec is not None and timeout_sec <= 0 else timeout_sec,
    )
    return {
        "commandType": command_types[0] if len(command_types) == 1 else None,
        "commandTypes": command_types,
        "engineSessionKey": session_key,
        "filters": filters,
        "response": response,
    }


def raw_command(payload: dict[str, Any]) -> dict[str, Any]:
    command = payload.get("command")
    if isinstance(command, dict):
        if not command.get("taskId") and payload.get("taskId"):
            command = {**command, "taskId": payload["taskId"]}
        if not command.get("taskId"):
            raise ValueError("taskId \u4e0d\u80fd\u4e3a\u7a7a")
        return command
    command = {key: value for key, value in payload.items() if key not in _ROUTING_KEYS}
    if not command.get("taskId"):
        command["taskId"] = _task_id(payload)
    if not command.get("commandType"):
        command["commandType"] = "executeAction"
    return command


def build_autocar_action(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("autocarAction"), list):
        return raw_command(payload)
    item: dict[str, Any] = {
        "autocarId": _int_or_raw(payload.get("autocarId") or payload.get("autoCarId") or payload.get("id") or 1),
        "instructionType": payload.get("instructionType") or payload.get("instruction_type") or "forward",
    }
    if payload.get("raw") is not None:
        item["raw"] = _float_from_payload(payload, "raw", default=0.0)
    location = payload.get("location")
    if isinstance(location, dict):
        item["location"] = location
    return {
        "commandType": payload.get("commandType") or "executeAction",
        "taskId": _task_id(payload),
        "autocarAction": [item],
    }


def build_carla_traffic_jam(payload: dict[str, Any]) -> dict[str, Any]:
    location_array = payload.get("locationArray") or payload.get("location_array")
    if not isinstance(location_array, list) or not location_array:
        raise ValueError("locationArray \u4e0d\u80fd\u4e3a\u7a7a")
    normalized_locations: list[dict[str, float]] = []
    for index, point in enumerate(location_array, start=1):
        if not isinstance(point, dict):
            raise ValueError(f"locationArray[{index}] \u5fc5\u987b\u662f JSON object")
        if point.get("x") is None or point.get("y") is None:
            raise ValueError(f"locationArray[{index}] \u5fc5\u987b\u5305\u542b x/y")
        normalized_locations.append(
            {
                "x": float(point["x"]),
                "y": float(point["y"]),
            }
        )
    return {
        "commandType": payload.get("commandType") or "trafficJam",
        "taskId": _task_id(payload),
        "locationArray": normalized_locations,
    }


def build_unmanned_dog_action(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("unmannedDogAction"), list):
        return raw_command(payload)
    item: dict[str, Any] = {
        "unmannedDogId": _int_or_raw(payload.get("unmannedDogId") or payload.get("dogId") or payload.get("id") or 1),
        "NavigationType": payload.get("NavigationType") or payload.get("navigationType") or "PathPlanning",
    }
    if isinstance(payload.get("PathPlanning"), dict):
        item["PathPlanning"] = payload["PathPlanning"]
    if isinstance(payload.get("Pathfinding"), dict):
        item["Pathfinding"] = payload["Pathfinding"]
    return {
        "commandType": payload.get("commandType") or "executeAction",
        "taskId": _task_id(payload),
        "unmannedDogAction": [item],
    }


def build_satellite_action(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("satelliteAction"), list):
        command = raw_command(payload)
        command.setdefault("instructionType", "satellite")
        return command
    item: dict[str, Any] = {
        "instructionType": _entity_action_instruction(payload, "satellite", "turnOn"),
        "satelliteId": _int_or_raw(payload.get("satelliteId") or payload.get("id") or 1),
    }
    if payload.get("lon") is not None:
        item["lon"] = _float_from_payload(payload, "lon", default=0.0)
    if payload.get("lat") is not None:
        item["lat"] = _float_from_payload(payload, "lat", default=0.0)
    return {
        "commandType": payload.get("commandType") or "executeAction",
        "taskId": _task_id(payload),
        "instructionType": "satellite",
        "satelliteAction": [item],
    }


def build_ship_action(payload: dict[str, Any]) -> dict[str, Any]:
    if isinstance(payload.get("shipAction"), list):
        command = raw_command(payload)
        command.setdefault("instructionType", "ship")
        return command
    item = {
        "instructionType": _entity_action_instruction(payload, "ship", "EntityMoveToS"),
        "shipId": _int_or_raw(payload.get("shipId") or payload.get("id") or 1),
        "locationArray": _location_array(payload),
    }
    return {
        "commandType": payload.get("commandType") or "executeAction",
        "taskId": _task_id(payload),
        "instructionType": "ship",
        "shipAction": [item],
    }


def build_plane_action(payload: dict[str, Any]) -> dict[str, Any]:
    plane_action = payload.get("plane")
    if isinstance(plane_action, list):
        command = raw_command(payload)
        command.setdefault("instructionType", "plane")
        return command
    item = {
        "instructionType": _entity_action_instruction(payload, "plane", "EntityMoveTo"),
        "planeId": _int_or_raw(payload.get("planeId") or payload.get("id") or 1),
        "locationArray": _location_array(payload),
    }
    return {
        "commandType": payload.get("commandType") or "executeAction",
        "taskId": _task_id(payload),
        "instructionType": "plane",
        "plane": [item],
    }


def _entity_action_instruction(payload: dict[str, Any], entity_type: str, default: str) -> str:
    explicit = (
        payload.get("actionInstructionType")
        or payload.get("action_instruction_type")
        or payload.get(f"{entity_type}InstructionType")
        or payload.get(f"{entity_type}_instruction_type")
    )
    if explicit:
        return str(explicit)
    instruction = payload.get("instructionType") or payload.get("instruction_type")
    if instruction and str(instruction) != entity_type:
        return str(instruction)
    return default


def _location_array(payload: dict[str, Any]) -> list[dict[str, float]]:
    location_array = payload.get("locationArray") or payload.get("location_array")
    if isinstance(location_array, list) and location_array:
        return [dict(item) for item in location_array if isinstance(item, dict)]
    location = payload.get("location")
    if isinstance(location, dict):
        return [dict(location)]
    return [
        {
            "lon": _float_from_payload(payload, "lon", default=0.0),
            "lat": _float_from_payload(payload, "lat", default=0.0),
            "alt": _float_from_payload(payload, "alt", default=0.0),
        }
    ]


def build_get_engine_loc(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "commandType": payload.get("commandType") or "getEngineLoc",
        "taskId": _task_id(payload),
    }


def build_take_photo(payload: dict[str, Any]) -> dict[str, Any]:
    task_id = _task_id(payload)
    model_id_list = payload.get("modelIdList") or payload.get("model_id_list")
    if isinstance(model_id_list, dict):
        model_id_list = [model_id_list]
    if not isinstance(model_id_list, list) or not model_id_list:
        model_id_list = [{"droneId": payload.get("droneId") or "drone1"}]
    photo_metadata = {
        key: payload[key]
        for key in ("agentId", "agentType", "viewType", "analysisType", "stepIndex")
        if payload.get(key) is not None
    }
    photo_metadata.update(
        {
            camel: payload[snake]
            for camel, snake in {
                "agentId": "agent_id",
                "agentType": "agent_type",
                "viewType": "view_type",
                "analysisType": "analysis_type",
                "stepIndex": "step_index",
            }.items()
            if payload.get(snake) is not None and camel not in photo_metadata
        }
    )
    if photo_metadata:
        model_id_list = [
            {**photo_metadata, **item} if isinstance(item, dict) else item
            for item in model_id_list
        ]
    model_id_list = [_with_photo_id(task_id, item) for item in model_id_list]
    return {
        "commandType": payload.get("commandType") or "takePhoto",
        "taskId": task_id,
        "modelIdList": model_id_list,
    }


def build_scenario_command(payload: dict[str, Any]) -> dict[str, Any]:
    from app.modules.envs.scenario import ScenarioSpec

    scenario_payload = payload.get("scenario")
    if scenario_payload is None and "equipmentList" in payload and "taskMatrix" in payload:
        scenario_payload = {
            key: value
            for key, value in payload.items()
            if key not in _ROUTING_KEYS | {"taskId", "task_id", "commandType"}
        }
    if not isinstance(scenario_payload, dict):
        raise ValueError("scenario \u4e0d\u80fd\u4e3a\u7a7a\uff0c\u6216\u8bf7\u6c42\u4f53\u672c\u8eab\u5fc5\u987b\u5305\u542b equipmentList/taskMatrix")

    spec = ScenarioSpec.from_obj(scenario_payload)
    spec.task_id = _task_id(payload)
    return {
        "commandType": "resetScenario",
        "taskId": spec.task_id,
        "scenario": spec.to_engine_payload(),
    }


def build_task_complete_command(payload: dict[str, Any]) -> dict[str, Any]:
    """\u6784\u9020"\u4efb\u52a1\u5b8c\u6210"\u4e0b\u53d1\u6307\u4ee4: ``{commandType:"complete", taskId}``\u3002

    \u5916\u90e8 HTTP \u8c03 ``/sim/engine/task-complete`` \u65f6\u7528; \u9ed8\u8ba4\u5c31\u53d1 ``{"commandType":"complete","taskId":...}``
    \u8fd9\u4e24\u4e2a\u5b57\u6bb5\u3002\u5982\u8c03\u7528\u65b9\u989d\u5916\u5e26 success/result/message \u7b49\u5b57\u6bb5, \u4e5f\u4f1a\u539f\u6837\u900f\u4f20; ``commandType`` \u53ef\u8986\u76d6\u3002
    """

    command: dict[str, Any] = {
        "commandType": str(payload.get("commandType") or payload.get("command_type") or "complete"),
        "taskId": _task_id(payload),
    }
    skip = _ROUTING_KEYS | {"taskId", "task_id", "commandType", "command_type"}
    for key, value in payload.items():
        if key not in skip:
            command[key] = value
    return command
