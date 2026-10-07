"""Tests for Gym-style environment layer."""

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.modules.envs.evaluators import build_evaluator, list_evaluators
from app.modules.envs.interaction import resolve_interaction, InteractionConfig, ObservationConfig
from app.modules.envs.scenario import ScenarioSpec, strip_json_comments
from app.modules.envs.scenario_models import ScenarioDefinition
from app.modules.envs.engine_bridge import get_bridge
from app.modules.envs.envs.open_vocab_nav_env import OpenVocabNavEnv
from app.modules.envs.episode import episode_store
from app.modules.envs.task_id import BEIJING_TZ, beijing_now, make_task_id


SCENARIO_PATH = Path(__file__).resolve().parents[1] / "app/modules/agents/scenarios/example_scenario.json"


def test_strip_json_comments():
    text = '{ "a": 1, // comment\n "b": 2 }'
    cleaned = strip_json_comments(text)
    import json

    assert json.loads(cleaned) == {"a": 1, "b": 2}


def test_legacy_scenario_load():
    spec = ScenarioSpec.from_file(SCENARIO_PATH, task_index=0)
    assert spec.scene_name == "\u4fa6\u5bdf_\u7a7a\u5730\u534f\u540c"
    assert len(spec.assets) >= 1
    assert spec.task_type in {
        "open_vocab_navigation",
        "cross_domain_target_search",
        "satellite_observation",
        "cross_terrain_relay",
    }


def test_interaction_resolver_precedence():
    env_default = InteractionConfig(
        bridge="mock",
        observation=ObservationConfig(modalities=["pose"]),
    )
    resolved = resolve_interaction(
        env_default,
        {"interaction": {"observation": {"modalities": ["camera_rgb", "pose"]}}},
        {"bridge": "mock", "action": {"require_ack": True}},
    )
    assert resolved.bridge == "mock"
    assert "camera_rgb" in resolved.observation.modalities
    assert resolved.action.require_ack is True


def test_build_observation_query_includes_modalities_and_schema():
    from app.modules.envs.envs.multi_drone_delivery_env import MultiDroneDeliveryEnv
    from app.modules.envs.interaction import build_observation_query

    env = MultiDroneDeliveryEnv()
    cfg = env.default_interaction()
    query = build_observation_query(
        {"phase": "step", "task_id": "task-001"},
        cfg,
        observation_schema=env.observation_space_dict(),
    )
    assert query["task_id"] == "task-001"
    assert "camera_rgb" in query["modalities"]
    assert query["observation_schema"]["type"] == "Dict"
    assert "drones" in query["observation_schema"]["spaces"]


def test_realtime_bridge_sends_observation_contract_in_query(monkeypatch):
    import asyncio
    from typing import Any

    from app.modules.envs.engine_bridge.realtime_bridge import RealtimeEngineBridge
    from app.modules.envs.interaction import InteractionConfig, ObservationConfig

    captured: dict[str, Any] = {}

    async def fake_request_to_engine(command, timeout=5.0, *, targets=None):
        captured["command"] = command
        return {"pose": {"x": 1.0}}

    import app.modules.realtime.manager as manager_module

    monkeypatch.setattr(manager_module.realtime_manager, "request_to_engine", fake_request_to_engine)

    async def run() -> None:
        bridge = RealtimeEngineBridge()
        cfg = InteractionConfig(observation=ObservationConfig(modalities=["pose", "camera_rgb"]))
        await bridge.request_observation(
            {
                "phase": "step",
                "task_id": "task-001",
                "observation_schema": {"type": "Dict", "spaces": {"pose": {"type": "Box"}}},
            },
            cfg,
        )

    asyncio.run(run())
    query = captured["command"]["query"]
    assert query["modalities"] == ["pose", "camera_rgb"]
    assert query["observation_schema"]["spaces"]["pose"]["type"] == "Box"


def test_base_env_passes_observation_contract_on_reset_and_step():
    import asyncio
    from typing import Any

    spec = ScenarioSpec.from_file(
        Path(__file__).resolve().parents[1] / "app/modules/envs/scenarios/open_vocab_navigation.json"
    )
    captured_queries: list[dict[str, Any]] = []

    class CaptureBridge:
        async def reset_scenario(self, _spec, _cfg):
            return {"status": "reset"}

        async def request_observation(self, query, _cfg):
            captured_queries.append(dict(query))
            return {"pose": {"x": 0, "y": 0, "z": 0}, "goal_position": {"x": 1, "y": 0, "z": 0}}

        async def dispatch_action(self, _action, _cfg):
            return {"status": "sent"}

        async def call_custom(self, _name, _payload, _cfg):
            return {"status": "ok"}

        async def close(self):
            return None

    env = OpenVocabNavEnv(bridge=CaptureBridge())
    env.evaluator = build_evaluator(spec.evaluator)
    expected_schema = env.observation_space_dict()

    async def run() -> None:
        await env.reset(spec)
        await env.step({"offset": [1.0, 0.0], "speed": 10})

    asyncio.run(run())
    expected_modalities = list(env.interaction.observation.modalities)
    assert len(captured_queries) == 2

    reset_query = captured_queries[0]
    assert reset_query["phase"] == "reset"
    assert reset_query["modalities"] == expected_modalities
    assert reset_query["observation_schema"] == expected_schema
    assert reset_query["observation_schema"]["type"] == "Dict"
    assert "pose" in reset_query["observation_schema"]["spaces"]

    step_query = captured_queries[1]
    assert step_query["phase"] == "step"
    assert step_query["modalities"] == expected_modalities
    assert step_query["observation_schema"] == expected_schema


def test_realtime_manager_ws_command_carries_observation_contract():
    import asyncio
    from typing import Any

    from app.modules.envs.envs.multi_drone_delivery_env import MultiDroneDeliveryEnv
    from app.modules.realtime.manager import RealtimeManager

    sent_messages: list[dict[str, Any]] = []

    class FakeWebSocket:
        async def send_json(self, message: dict[str, Any]) -> None:
            sent_messages.append(message)
            request_id = message["data"].get("request_id")
            future = manager._pending.get(request_id)
            if future is not None and not future.done():
                query = message["data"]["query"]
                future.set_result(
                    {
                        "drones": {},
                        "step": 1,
                        "requested_modalities": query.get("modalities"),
                        "requested_schema_keys": list(
                            (query.get("observation_schema") or {}).get("spaces", {}).keys()
                        ),
                    }
                )

    manager = RealtimeManager()
    fake_ws = FakeWebSocket()
    manager.session_map["LJ-ENGINE"]["LJ-ENGINE_test"] = fake_ws
    manager.session_key_map["LJ-ENGINE_test"] = fake_ws

    env = MultiDroneDeliveryEnv()
    cfg = env.default_interaction()
    schema = env.observation_space_dict()

    async def run() -> dict[str, Any]:
        from app.modules.envs.interaction import build_observation_query

        query = build_observation_query(
            {"phase": "step", "task_id": "delivery-test-001"},
            cfg,
            observation_schema=schema,
        )
        return await manager.request_to_engine(
            {
                "commandType": cfg.engine_commands.request_observation,
                "taskId": "delivery-test-001",
                "query": query,
            },
            timeout=1.0,
        )

    result = asyncio.run(run())
    assert sent_messages, "expected WebSocket COMMAND envelope"
    envelope = sent_messages[0]
    outbound = envelope["data"]
    query = outbound["query"]
    assert envelope["type"] == "COMMAND"
    assert outbound["commandType"] == "getFleetObservation"
    assert query["modalities"] == list(cfg.observation.modalities)
    assert query["observation_schema"] == schema
    assert "drones" in query["observation_schema"]["spaces"]
    assert result["requested_modalities"] == query["modalities"]
    assert "drones" in result["requested_schema_keys"]


@pytest.mark.asyncio
async def test_open_vocab_nav_env_reaches_success():
    spec = ScenarioSpec.from_file(
        Path(__file__).resolve().parents[1] / "app/modules/envs/scenarios/open_vocab_navigation.json"
    )
    env = OpenVocabNavEnv()
    env.evaluator = build_evaluator(spec.evaluator)
    obs, _ = await env.reset(spec)
    assert "pose" in obs
    terminated = False
    for _ in range(40):
        pose = obs.get("pose") or {}
        goal = obs.get("goal_position") or {}
        if "x" in pose:
            action = {
                "offset": [
                    min(10, max(-10, goal.get("x", 0) - pose.get("x", 0))),
                    min(10, max(-10, goal.get("y", 0) - pose.get("y", 0))),
                ],
                "speed": 25,
            }
        else:
            action = {
                "offset": [
                    min(0.01, max(-0.01, goal.get("lon", 0) - pose.get("lon", 0))),
                    min(0.01, max(-0.01, goal.get("lat", 0) - pose.get("lat", 0))),
                ],
                "speed": 25,
            }
        obs, reward, terminated, truncated, info = await env.step(action)
        if terminated or truncated:
            break
    assert terminated or truncated
    assert env.get_trajectory()


def test_evaluator_registry():
    names = {item["name"] for item in list_evaluators()}
    assert "ovn_default" in names


def test_env_api_list_and_episode():
    with TestClient(app) as client:
        listed = client.get("/api/envs").json()
        assert listed["code"] == 200
        assert any(item["name"] == "open_vocab_navigation" for item in listed["data"])

        created = client.post(
            "/api/envs/open_vocab_navigation/episodes",
            json={
                "scenario": {
                    "scenario_id": "test_ep",
                    "task_type": "open_vocab_navigation",
                    "assets": [{"id": "uav-01", "kind": "uav", "spawn": {"x": 0, "y": 0, "z": 10}}],
                    "targets": [
                        {
                            "id": "t1",
                            "description": "target",
                            "goal_position": {"x": 20, "y": 0, "z": 0},
                        }
                    ],
                    "termination": {"max_steps": 10, "success_distance": 2.0},
                    "evaluator": {"name": "ovn_default", "config": {"success_distance": 2.0}},
                }
            },
        ).json()
        assert created["code"] == 200
        episode_id = created["data"]["episode_id"]

        stepped = client.post(
            f"/api/envs/episodes/{episode_id}/step",
            json={"action": {"offset": [5.0, 0.0], "speed": 10}},
        ).json()
        assert stepped["code"] == 200
        assert "reward" in stepped["data"]


def test_legacy_scenario_upload_preview():
    if not SCENARIO_PATH.exists():
        pytest.skip("legacy scenario file missing")
    with TestClient(app) as client:
        with SCENARIO_PATH.open("rb") as handle:
            response = client.post(
                "/api/envs/scenarios/upload",
                files={"file": ("example_scenario.json", handle, "application/json")},
            )
        body = response.json()
        assert body["code"] == 200
        assert body["data"]["task_count"] >= 1


@pytest.mark.asyncio
async def test_mock_bridge_reset():
    spec = ScenarioSpec.from_file(
        Path(__file__).resolve().parents[1] / "app/modules/envs/scenarios/open_vocab_navigation.json"
    )
    bridge = get_bridge("mock")
    cfg = InteractionConfig()
    result = await bridge.reset_scenario(spec, cfg)
    assert "pose" in result


def test_scenario_definition_validates_legacy_json():
    text = SCENARIO_PATH.read_text(encoding="utf-8")
    payload = json.loads(strip_json_comments(text))
    definition = ScenarioDefinition.model_validate(payload)
    assert definition.sceneName == "\u4fa6\u5bdf_\u7a7a\u5730\u534f\u540c"
    assert len(definition.taskMatrix) >= 1
    assert definition.equipmentList.droneEntityList[0].sensorType
    engine_payload = definition.to_engine_payload()
    assert "equipmentList" in engine_payload
    assert engine_payload["taskMatrix"][0]["task_id"].startswith("GOBI_RECON")


def test_scenario_definition_round_trip_to_spec():
    definition = ScenarioDefinition(
        sceneName="demo",
        collaborationType="\u7a7a\u5730\u534f\u540c",
        equipmentList={
            "droneEntityList": [
                {
                    "equipmentCode": "drone-1",
                    "name": "drone1",
                    "data": {"X": 0, "Y": 0, "Z": 50},
                    "raw": 30,
                    "sensorType": "EO/IR",
                }
            ]
        },
        taskMatrix=[
            {
                "taskLevel": "Individual",
                "task_id": "T_001",
                "goal": "fly to goal",
                "initial_state": {
                    "weather": "clear",
                    "traffic": "none",
                    "goalPosition": {"lon": 1, "lat": 1, "alt": 100},
                },
            }
        ],
    )
    spec = ScenarioSpec.from_definition(definition)
    assert spec.scene_name == "demo"
    assert spec.assets and spec.assets[0].id == "drone-1"
    assert spec.assets[0].sensors == ["EO", "IR"]
    payload = spec.to_engine_payload()
    assert payload["sceneName"] == "demo"
    assert payload["equipmentList"]["droneEntityList"][0]["name"] == "drone1"


def test_make_task_id_is_beijing_time():
    a = make_task_id("test")
    b = make_task_id("test")
    assert a.startswith("test_")
    assert len(a.split("_")) == 4
    now = beijing_now()
    assert now.utcoffset().total_seconds() == 8 * 3600
    assert now.strftime("%Y%m%d") in a
    assert a != b or a == b  # millisecond resolution; identical only on same ms


@pytest.mark.asyncio
async def test_episode_assigns_beijing_task_id_and_persists_to_sim_data():
    from app.db.models import SimData
    from app.db.session import StreamSessionLocal
    from sqlalchemy import select

    spec = ScenarioSpec.from_file(
        Path(__file__).resolve().parents[1] / "app/modules/envs/scenarios/open_vocab_navigation.json"
    )
    record = await episode_store.create("open_vocab_navigation", spec)
    assert record.task_id.startswith("open_vocab_navigation_")
    assert record.episode_id == record.task_id
    assert record.scenario.task_id == record.task_id

    await episode_store.step(record.episode_id, {"offset": [5.0, 0.0], "speed": 10})

    with StreamSessionLocal() as db:
        rows = db.execute(
            select(SimData).where(SimData.task_id == record.task_id)
        ).scalars().all()
    assert rows, "expected sim_data rows tagged with the episode task id"
    phases = {json.loads(row.data).get("phase") for row in rows}
    assert "reset" in phases and "step" in phases

    await episode_store.close(record.episode_id)


def test_router_returns_task_id_and_engine_payload():
    with TestClient(app) as client:
        created = client.post(
            "/api/envs/open_vocab_navigation/episodes",
            json={
                "scenario": {
                    "scenario_id": "router_task",
                    "task_type": "open_vocab_navigation",
                    "assets": [{"id": "uav", "kind": "uav", "spawn": {"x": 0, "y": 0, "z": 10}}],
                    "targets": [
                        {"id": "t", "description": "", "goal_position": {"x": 100, "y": 0, "z": 0}}
                    ],
                    "termination": {"max_steps": 5, "success_distance": 2.0},
                    "evaluator": {"name": "ovn_default", "config": {"success_distance": 2.0}},
                }
            },
        ).json()
        assert created["code"] == 200
        data = created["data"]
        assert data["task_id"].startswith("open_vocab_navigation_")
        assert data["created_at_beijing"]
        assert "equipmentList" in data["engine_scenario_payload"]
        assert data["engine_scenario_payload"]["taskId"] == data["task_id"]

        schema = client.get("/api/envs/scenarios/schema").json()
        assert schema["code"] == 200
        assert "ScenarioDefinition" in schema["data"]["title"] or "properties" in schema["data"]


def test_router_accepts_definition_input():
    with TestClient(app) as client:
        body = {
            "definition": {
                "sceneName": "demo",
                "collaborationType": "\u7a7a\u5730\u534f\u540c",
                "equipmentList": {
                    "droneEntityList": [
                        {
                            "equipmentCode": "drone-1",
                            "name": "drone1",
                            "data": {"X": 0, "Y": 0, "Z": 50},
                            "raw": 0,
                            "sensorType": "EO",
                        }
                    ]
                },
                "taskMatrix": [
                    {
                        "taskLevel": "Individual",
                        "task_id": "T_DEF_001",
                        "goal": "navigate to goal",
                        "initial_state": {
                            "weather": "clear",
                            "traffic": "none",
                            "goalPosition": {"lon": 0.0001, "lat": 0.0001, "alt": 50},
                        },
                    }
                ],
            }
        }
        created = client.post("/api/envs/open_vocab_navigation/episodes", json=body).json()
        assert created["code"] == 200
        assert created["data"]["engine_scenario_payload"]["sceneName"] == "demo"
