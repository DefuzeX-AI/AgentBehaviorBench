"""Business logic for Java-compatible simulation CRUD endpoints."""

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.converters import normalize_payload, require_text, update_present_fields
from app.db.models import SimData, SimScene, SimSceneInstance, SimTask


def _now() -> datetime:
    """Return the timestamp used for Java `createTime` and `updateTime` fields."""

    return datetime.now()


def _one_or_error(db: Session, model: type, message: str, **filters: Any) -> Any:
    """Fetch one ORM row or raise the same business error as the Java service."""

    stmt = select(model)
    for field, value in filters.items():
        stmt = stmt.where(getattr(model, field) == value)
    result = db.execute(stmt).scalars().first()
    if result is None:
        raise RuntimeError(message)
    return result


def _delete_or_error(db: Session, model: type, message: str, **filters: Any) -> None:
    """Delete rows by filters and fail if Java would have reported missing data."""

    stmt = delete(model)
    for field, value in filters.items():
        stmt = stmt.where(getattr(model, field) == value)
    if db.execute(stmt).rowcount <= 0:
        raise RuntimeError(message)


def save_scene(db: Session, payload: dict[str, Any]) -> SimScene:
    """Create a scene or update the existing one with the same `sceneCode`."""

    data = normalize_payload(payload)
    require_text(data.get("scene_name"), "\u573a\u666f\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    require_text(data.get("scene_code"), "\u573a\u666f\u7f16\u53f7\u4e0d\u80fd\u4e3a\u7a7a")
    existing = db.execute(
        select(SimScene).where(SimScene.scene_code == data["scene_code"])
    ).scalars().first()
    if existing:
        existing.scene_name = data.get("scene_name")
        existing.update_time = _now()
        return existing
    scene = SimScene(
        **{k: data.get(k) for k in {"scene_name", "scene_code"}},
        create_time=_now(),
        update_time=_now(),
    )
    db.add(scene)
    db.flush()
    return scene


def update_scene(db: Session, payload: dict[str, Any]) -> SimScene:
    """Update a scene by primary key, matching `SimSceneServiceImpl.update`."""

    data = normalize_payload(payload)
    if data.get("id") is None:
        raise ValueError("\u4eff\u771f\u573a\u666f\u548cID\u4e0d\u80fd\u4e3a\u7a7a")
    scene = _one_or_error(db, SimScene, "\u4eff\u771f\u573a\u666f\u4e0d\u5b58\u5728", id=data["id"])
    update_present_fields(scene, data, {"scene_name", "scene_code"})
    scene.update_time = _now()
    return scene


def save_task(db: Session, payload: dict[str, Any]) -> SimTask:
    """Create a task or update the existing one with the same `taskCode`."""

    data = normalize_payload(payload)
    require_text(data.get("task_name"), "\u4efb\u52a1\u540d\u79f0\u4e0d\u80fd\u4e3a\u7a7a")
    require_text(data.get("task_code"), "\u4efb\u52a1\u7f16\u53f7\u4e0d\u80fd\u4e3a\u7a7a")
    existing = db.execute(
        select(SimTask).where(SimTask.task_code == data["task_code"])
    ).scalars().first()
    fields = {"task_name", "scene_id", "status", "description", "start_time", "end_time"}
    if existing:
        update_present_fields(existing, data, fields)
        existing.update_time = _now()
        return existing
    task = SimTask(
        **{k: data.get(k) for k in fields | {"task_code"}},
        create_time=_now(),
        update_time=_now(),
    )
    db.add(task)
    db.flush()
    return task


def update_task(db: Session, payload: dict[str, Any]) -> SimTask:
    """Patch a task by id, preserving unspecified fields."""

    data = normalize_payload(payload)
    if data.get("id") is None:
        raise ValueError("\u4eff\u771f\u4efb\u52a1\u548cID\u4e0d\u80fd\u4e3a\u7a7a")
    task = _one_or_error(db, SimTask, "\u4eff\u771f\u4efb\u52a1\u4e0d\u5b58\u5728", id=data["id"])
    update_present_fields(
        task,
        data,
        {"task_name", "task_code", "scene_id", "status", "description", "start_time", "end_time"},
    )
    task.update_time = _now()
    return task


def save_instance(db: Session, payload: dict[str, Any]) -> SimSceneInstance:
    """Create or update a scene instance when the request already carries `id`."""

    data = normalize_payload(payload)
    if data.get("scene_id") is None:
        raise ValueError("\u573a\u666fID\u4e0d\u80fd\u4e3a\u7a7a")
    if data.get("id") is not None:
        existing = db.get(SimSceneInstance, data["id"])
        if existing is not None:
            return update_instance(db, payload)
    instance = SimSceneInstance(
        **{k: data.get(k) for k in {"scene_id", "name", "data", "type"}},
        create_time=_now(),
        update_time=_now(),
    )
    db.add(instance)
    db.flush()
    return instance


def update_instance(db: Session, payload: dict[str, Any]) -> SimSceneInstance:
    """Patch a scene instance by id."""

    data = normalize_payload(payload)
    if data.get("id") is None:
        raise ValueError("\u4eff\u771f\u573a\u666f\u5b9e\u4f8b\u548cID\u4e0d\u80fd\u4e3a\u7a7a")
    instance = _one_or_error(db, SimSceneInstance, "\u4eff\u771f\u573a\u666f\u5b9e\u4f8b\u4e0d\u5b58\u5728", id=data["id"])
    update_present_fields(instance, data, {"scene_id", "name", "data", "type"})
    instance.update_time = _now()
    return instance


def save_sim_data(db: Session, payload: dict[str, Any]) -> SimData:
    """Persist simulation data without the Java bug that overwrote `taskId`."""

    data = normalize_payload(payload)
    sim_data = SimData(
        task_id=data.get("task_id"),
        data=data.get("data"),
        create_time=_now(),
        update_time=_now(),
    )
    db.add(sim_data)
    db.flush()
    return sim_data


def update_sim_data(db: Session, payload: dict[str, Any]) -> SimData:
    """Patch a simulation data record by id."""

    data = normalize_payload(payload)
    if data.get("id") is None:
        raise ValueError("\u4eff\u771f\u6570\u636e\u548cID\u4e0d\u80fd\u4e3a\u7a7a")
    sim_data = _one_or_error(db, SimData, "\u4eff\u771f\u6570\u636e\u4e0d\u5b58\u5728", id=data["id"])
    update_present_fields(sim_data, data, {"task_id", "data"})
    sim_data.update_time = _now()
    return sim_data


def get_sim_data_page(db: Session, scene_id: str, page_num: int, page_size: int) -> dict[str, Any]:
    """Return a MyBatis-Plus-like page object for the legacy `getBySceneId` API."""

    if not scene_id:
        raise ValueError("\u573a\u666fID\u4e0d\u80fd\u4e3a\u7a7a")
    page_num = max(page_num or 1, 1)
    page_size = max(page_size or 10, 1)
    base = select(SimData).where(SimData.task_id == scene_id)
    total = len(db.execute(base).scalars().all())
    records = db.execute(
        base.order_by(SimData.create_time.desc())
        .offset((page_num - 1) * page_size)
        .limit(page_size)
    ).scalars().all()
    pages = (total + page_size - 1) // page_size if page_size else 0
    return {
        "records": records,
        "total": total,
        "size": page_size,
        "current": page_num,
        "pages": pages,
    }


def delete_by_id(db: Session, model: type, id_value: int, message: str) -> None:
    """Shared delete-by-id helper for the Java controller routes."""

    if id_value is None:
        raise ValueError("ID\u4e0d\u80fd\u4e3a\u7a7a")
    _delete_or_error(db, model, message, id=id_value)


def delete_by_field(db: Session, model: type, message: str, **filters: Any) -> None:
    """Shared delete-by-field helper for code and task-id based deletes."""

    for value in filters.values():
        if value is None or (isinstance(value, str) and not value.strip()):
            raise ValueError("\u53c2\u6570\u4e0d\u80fd\u4e3a\u7a7a")
    _delete_or_error(db, model, message, **filters)


def _build_test_interaction(payload: dict[str, Any]):
    """Resolve InteractionConfig for test routes (defaults to realtime bridge)."""

    from app.modules.envs.interaction import InteractionConfig, resolve_interaction

    override = payload.get("interaction")
    episode_override = override if isinstance(override, dict) else None
    return resolve_interaction({"bridge": "realtime"}, episode_override=episode_override)


def _parse_test_scenario(payload: dict[str, Any]):
    """Parse user \u60f3\u5b9a JSON into ScenarioSpec, same rules as env episode API."""

    from app.modules.envs.router import _parse_scenario_payload
    from app.modules.envs.scenario import ScenarioSpec
    from app.modules.envs.task_id import make_task_id

    spec = _parse_scenario_payload(payload)
    task_id = payload.get("taskId") or payload.get("task_id")
    if task_id:
        spec.task_id = str(task_id)
    elif not spec.task_id:
        spec.task_id = make_task_id("test")
    return spec


def _require_task_id(payload: dict[str, Any]) -> str:
    task_id = payload.get("taskId") or payload.get("task_id")
    if not task_id:
        raise ValueError("taskId \u4e0d\u80fd\u4e3a\u7a7a")
    return str(task_id)


async def test_reset_scenario(payload: dict[str, Any]) -> dict[str, Any]:
    """Test helper: reset via RealtimeEngineBridge (production WebSocket flow)."""

    from app.modules.envs.engine_bridge import get_bridge

    spec = _parse_test_scenario(payload)
    cfg = _build_test_interaction(payload)
    response = await get_bridge(cfg.bridge).reset_scenario(spec, cfg)
    return {
        "taskId": spec.task_id,
        "commandType": "resetScenario",
        "requiresAck": True,
        "engineScenarioPayload": spec.to_engine_payload(),
        "resolvedInteraction": cfg.to_dict(),
        "response": response,
    }


async def test_request_observation(payload: dict[str, Any]) -> dict[str, Any]:
    """Test helper: pull observation via RealtimeEngineBridge RPC (always waits for ack)."""

    from app.modules.envs.engine_bridge import get_bridge

    task_id = _require_task_id(payload)
    cfg = _build_test_interaction(payload)
    query = dict(payload.get("query") or {})
    query.setdefault("task_id", task_id)
    observation_schema = payload.get("observation_schema") or payload.get("observationSchema")
    if observation_schema is not None:
        query["observation_schema"] = observation_schema
    observation = await get_bridge(cfg.bridge).request_observation(query, cfg)
    return {
        "taskId": task_id,
        "commandType": cfg.engine_commands.request_observation,
        "requiresAck": True,
        "resolvedInteraction": cfg.to_dict(),
        "observation": observation,
    }


async def test_dispatch_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Test helper: dispatch action via RealtimeEngineBridge (ack controlled by InteractionConfig)."""

    from app.modules.envs.engine_bridge import get_bridge

    task_id = _require_task_id(payload)
    action = payload.get("action")
    if not isinstance(action, dict):
        raise ValueError("action \u4e0d\u80fd\u4e3a\u7a7a")
    cfg = _build_test_interaction(payload)
    action_payload = {**action, "task_id": task_id, "taskId": task_id}
    ack = await get_bridge(cfg.bridge).dispatch_action(action_payload, cfg)
    return {
        "taskId": task_id,
        "commandType": cfg.engine_commands.execute_action,
        "requiresAck": cfg.action.require_ack,
        "resolvedInteraction": cfg.to_dict(),
        "ack": ack,
    }
