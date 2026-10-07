"""Smoke tests for the Java-compatible FastAPI surface."""

import json

from fastapi.testclient import TestClient

from app.main import app


def test_health_response_shape():
    """Health responses should use the global `{code,data,msg}` envelope."""

    with TestClient(app) as client:
        response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"code": 200, "data": {"status": "ok"}, "msg": "\u8bf7\u6c42\u6210\u529f"}


def test_scene_create_update_and_query():
    """Scene save should create first, then update by the same `sceneCode`."""

    with TestClient(app) as client:
        created = client.post(
            "/sim/scene/save",
            json={"sceneName": "\u573a\u666fA", "sceneCode": "scene-a"},
        ).json()
        assert created["code"] == 200
        assert created["data"]["sceneName"] == "\u573a\u666fA"
        assert created["data"]["sceneCode"] == "scene-a"

        updated = client.post(
            "/sim/scene/save",
            json={"sceneName": "\u573a\u666fB", "sceneCode": "scene-a"},
        ).json()
        assert updated["data"]["id"] == created["data"]["id"]
        assert updated["data"]["sceneName"] == "\u573a\u666fB"

        queried = client.get("/sim/scene/getBySceneCode", params={"sceneCode": "scene-a"}).json()
        assert queried["data"]["sceneName"] == "\u573a\u666fB"


def test_ai_endpoint_requires_internal_token():
    """The merged AI endpoint keeps the old bearer token requirement."""

    with TestClient(app) as client:
        response = client.post("/api/chat/image/analysis", json=[])
    assert response.status_code == 200
    assert response.json()["msg"] == "\u672a\u6388\u6743"


def test_langgraph_agent_registry_endpoint():
    """Agent discovery should work even before LangGraph is imported lazily."""

    with TestClient(app) as client:
        response = client.get("/api/agents")
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    names = {item["name"] for item in body["data"]}
    assert {
        "echo",
        "uav_recon",
        "uav_route_plan",
        "open_vocab_navigation",
        "embodied_vqa",
        "semantic_sequence_planning",
        "constraint_aware_planning",
        "cross_domain_target_search",
        "satellite_observation",
        "cross_terrain_relay",
    }.issubset(names)


def test_langgraph_echo_agent_invoke():
    """The echo agent should execute through a real compiled LangGraph graph."""

    with TestClient(app) as client:
        response = client.post(
            "/api/agents/echo/invoke",
            json={"input": "hello langgraph", "metadata": {"source": "test"}},
        )
    assert response.status_code == 200
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["input"] == "hello langgraph"
    assert body["data"]["output"] == "hello langgraph"
    assert body["data"]["metadata"]["source"] == "test"
    assert body["data"]["metadata"]["framework"] == "langgraph"


def test_single_agent_task_design_invoke():
    """A single-agent task should return plan commands and evaluation metrics."""

    with TestClient(app) as client:
        response = client.post(
            "/api/agents/open_vocab_navigation/invoke",
            json={
                "instruction": "\u5bfb\u627e\u4fa7\u7ffb\u7684\u7ea2\u8272\u6cb9\u7f50\u8f66",
                "asset_type": "uav",
                "search_regions": ["north_block", "main_road"],
            },
        )
    body = response.json()
    assert body["code"] == 200
    assert len(body["data"]["commands"]) == 2
    assert body["data"]["commands"][0]["commandType"] == "semanticNavigate"
    assert "SR" in body["data"]["evaluation_metrics"]
    assert body["data"]["metadata"]["graph"] == "open_vocab_navigation"


def test_multi_agent_task_design_invoke():
    """A multi-agent task should allocate terrain-specific relay assets."""

    with TestClient(app) as client:
        response = client.post(
            "/api/agents/cross_terrain_relay/invoke",
            json={
                "cargo": {"id": "med-kit"},
                "terrain_segments": [
                    {"name": "road_leg", "terrain": "road"},
                    {"name": "river_crossing", "terrain": "water"},
                    {"name": "mountain_terminal", "terrain": "vertical"},
                ],
                "available_assets": {
                    "ugv": ["ugv-01"],
                    "usv": ["boat-01"],
                    "uav": ["uav-01"],
                },
            },
        )
    body = response.json()
    assert body["code"] == 200
    assert [item["assigned_asset"] for item in body["data"]["relay_plan"]] == [
        "ugv-01",
        "boat-01",
        "uav-01",
    ]
    assert len(body["data"]["synchronization_plan"]) == 2
    assert body["data"]["metadata"]["graph"] == "cross_terrain_relay"


def test_uav_recon_agent_invoke(monkeypatch):
    """UAV recon should execute through its own LangGraph task file."""

    from app.modules.agents.tasks import uav_recon

    async def fake_analysis(payload):
        assert payload["type"] == "1"
        assert payload["imageBase64"] == "image-data"
        return json.dumps({"result": "true"})

    monkeypatch.setattr(uav_recon, "analysis", fake_analysis)

    with TestClient(app) as client:
        response = client.post(
            "/api/agents/uav_recon/invoke",
            json={"image_base64": "image-data", "metadata": {"source": "test"}},
        )
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["result"] is True
    assert body["data"]["parsed_response"]["result"] == "true"
    assert body["data"]["metadata"]["graph"] == "uav_recon"


def test_sim_test_engine_routes_use_realtime_bridge(monkeypatch):
    """Test routes should delegate to RealtimeEngineBridge, not custom WS logic."""

    from unittest.mock import AsyncMock, MagicMock

    mock_bridge = MagicMock()
    mock_bridge.reset_scenario = AsyncMock(return_value={"status": "reset"})
    mock_bridge.request_observation = AsyncMock(return_value={"pose": {"x": 1.0}})
    mock_bridge.dispatch_action = AsyncMock(return_value={"status": "sent"})

    monkeypatch.setattr(
        "app.modules.envs.engine_bridge.get_bridge",
        lambda _name: mock_bridge,
    )

    scenario = {
        "sceneName": "\u6d4b\u8bd5\u573a\u666f",
        "equipmentList": {"droneEntityList": [{"name": "drone1"}]},
        "taskMatrix": [{"taskLevel": "Individual", "goal": "\u6d4b\u8bd5\u76ee\u6807"}],
    }

    with TestClient(app) as client:
        reset_resp = client.post(
            "/sim/test/dispatchScenario",
            json={"scenario": scenario, "taskId": "test-task-001"},
        )
        observe_resp = client.post(
            "/sim/test/requestObservation",
            json={"taskId": "test-task-001", "query": {"modalities": ["pose"]}},
        )
        action_resp = client.post(
            "/sim/test/dispatchAction",
            json={"taskId": "test-task-001", "action": {"offset": [1.0, 0.0]}},
        )

    reset_body = reset_resp.json()
    assert reset_body["code"] == 200
    assert reset_body["data"]["taskId"] == "test-task-001"
    assert reset_body["data"]["requiresAck"] is True
    assert reset_body["data"]["response"]["status"] == "reset"
    mock_bridge.reset_scenario.assert_awaited_once()

    observe_body = observe_resp.json()
    assert observe_body["code"] == 200
    assert observe_body["data"]["requiresAck"] is True
    assert observe_body["data"]["observation"]["pose"]["x"] == 1.0
    mock_bridge.request_observation.assert_awaited_once()

    action_body = action_resp.json()
    assert action_body["code"] == 200
    assert action_body["data"]["requiresAck"] is False
    assert action_body["data"]["ack"]["status"] == "sent"
    mock_bridge.dispatch_action.assert_awaited_once()


def test_uav_route_plan_agent_invoke(monkeypatch):
    """UAV route planning should build messages, parse output, and dispatch commands."""

    from app.modules.agents.tasks import uav_route_plan

    dispatched = []

    async def fake_analysis(messages):
        assert messages[0]["content"][1]["image_url"]["url"] == "map-data"
        assert messages[0]["content"][2]["image_url"]["url"] == "image-data"
        return json.dumps({"status": "continue", "offset": [1.5, -2.0]})

    async def fake_send_by_user_type(message, user_type):
        dispatched.append((message, user_type))

    monkeypatch.setattr(uav_route_plan, "analysis", fake_analysis)
    monkeypatch.setattr(
        uav_route_plan.realtime_manager,
        "send_by_user_type",
        fake_send_by_user_type,
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/agents/uav_route_plan/invoke",
            json={
                "image_base64": "image-data",
                "map_base64": "map-data",
                "metadata": {"source": "test"},
            },
        )
    body = response.json()
    assert body["code"] == 200
    assert body["data"]["route_plan"]["status"] == "continue"
    assert body["data"]["dispatched_command"]["location"] == {"x": 1.5, "y": -2.0, "z": 0.0}
    assert dispatched[0][1] == "LJ-ENGINE"
