"""Tests for action dispatch_mode, retry, step_interval_sec, and RPC correlation."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.envs.engine_bridge.realtime_bridge import (
    RealtimeEngineBridge,
    agent_container_key,
    split_action_for_batched_mode,
)
from app.modules.envs.interaction import ActionConfig, InteractionConfig
from app.modules.envs.scenario import ScenarioSpec
from app.modules.realtime.manager import RealtimeManager


def test_agent_container_key_detects_drones_and_agents():
    assert agent_container_key({"drones": {"d1": {"offset": [1, 0]}}}) == "drones"
    assert agent_container_key({"agents": {"uav": {"offset": [0, 0]}}}) == "agents"
    assert agent_container_key({"offset": [1, 0]}) is None


def test_split_action_for_batched_mode():
    action = {
        "task_id": "task-001",
        "drones": {
            "drone1": {"offset": [1.0, 0.0]},
            "drone2": {"offset": [0.0, 2.0]},
        },
    }
    batches = split_action_for_batched_mode(action)
    assert len(batches) == 2
    assert batches[0]["agent"] == "drone1"
    assert batches[0]["drones"] == {"drone1": {"offset": [1.0, 0.0]}}
    assert batches[0]["task_id"] == "task-001"
    assert batches[1]["agent"] == "drone2"


@pytest.mark.asyncio
async def test_handle_message_resolves_rpc_by_request_id_without_whitelist():
    """Custom engine ack types (e.g. fire rescue) must complete pending RPC futures."""

    manager = RealtimeManager()
    loop = asyncio.get_running_loop()
    request_id = "corr-fire-001"
    future: asyncio.Future = loop.create_future()
    manager._pending[request_id] = future

    await manager.handle_message(
        "LJ-ENGINE_test",
        json.dumps(
            {
                "commandType": "fireRescueObservationResponse",
                "request_id": request_id,
                "data": {"agents": {"uav": {"pose": {"x": 1}}}},
            }
        ),
    )

    assert future.done()
    assert future.result() == {"agents": {"uav": {"pose": {"x": 1}}}}
    assert request_id not in manager._pending


@pytest.mark.asyncio
async def test_handle_message_resolves_rpc_with_requestId_camel_case():
    manager = RealtimeManager()
    loop = asyncio.get_running_loop()
    request_id = "corr-camel-002"
    future: asyncio.Future = loop.create_future()
    manager._pending[request_id] = future

    await manager.handle_message(
        "LJ-ENGINE_test",
        json.dumps(
            {
                "commandType": "fireRescueActionAck",
                "requestId": request_id,
                "data": {"status": "ok"},
            }
        ),
    )

    assert future.result() == {"status": "ok"}


@pytest.mark.asyncio
async def test_handle_message_push_engine_telemetry_persists():
    manager = RealtimeManager()
    with patch.object(manager, "persist_task_data") as mock_persist:
        await manager.handle_message(
            "LJ-ENGINE_test",
            json.dumps(
                {
                    "commandType": "pushEngineTelemetry",
                    "taskId": "task-telemetry-1",
                    "data": {"frame": 42, "poses": {"drone1": {"x": 1}}},
                }
            ),
        )
    mock_persist.assert_called_once()
    assert mock_persist.call_args[0][0] == "task-telemetry-1"
    assert mock_persist.call_args[0][1]["phase"] == "telemetry"


@pytest.mark.asyncio
async def test_handle_message_unknown_request_id_falls_through_to_routing():
    manager = RealtimeManager()
    ws = MagicMock()
    manager.session_map["LJ-UE"] = {"LJ-UE_x": ws}
    manager.session_key_map["LJ-UE_x"] = ws

    with patch.object(manager, "send_by_user_type", new_callable=AsyncMock) as mock_send:
        await manager.handle_message(
            "LJ-UE_x",
            json.dumps(
                {
                    "commandType": "sendToUE",
                    "request_id": "not-a-pending-rpc",
                    "command": {"foo": 1},
                }
            ),
        )

    mock_send.assert_awaited_once()


def test_resolve_lj_engine_targets_broadcast_vs_unicast():
    manager = RealtimeManager()
    ws_a = MagicMock()
    ws_b = MagicMock()
    manager.session_map["LJ-ENGINE"] = {
        "LJ-ENGINE_a": ws_a,
        "LJ-ENGINE_b": ws_b,
    }
    manager.session_key_map["LJ-ENGINE_a"] = ws_a
    manager.session_key_map["LJ-ENGINE_b"] = ws_b

    broadcast = manager.resolve_lj_engine_targets(dispatch_mode="broadcast")
    assert len(broadcast) == 2
    assert set(broadcast) == {ws_a, ws_b}

    unicast = manager.resolve_lj_engine_targets(dispatch_mode="unicast")
    assert len(unicast) == 1
    assert unicast[0] in {ws_a, ws_b}

    keyed = manager.resolve_lj_engine_targets(
        dispatch_mode="unicast", session_key="LJ-ENGINE_b"
    )
    assert keyed == [ws_b]


def test_ack_successful_respects_require_ack():
    assert RealtimeEngineBridge._ack_successful({"status": "sent"}, require_ack=False)
    assert RealtimeEngineBridge._ack_successful({"status": "ok"}, require_ack=True)
    assert not RealtimeEngineBridge._ack_successful({"status": "error"}, require_ack=True)
    assert not RealtimeEngineBridge._ack_successful(
        {"status": "ok", "error": "boom"}, require_ack=True
    )


@pytest.mark.asyncio
async def test_dispatch_action_retries_on_failure():
    bridge = RealtimeEngineBridge()
    cfg = InteractionConfig(
        bridge="realtime",
        action=ActionConfig(require_ack=True, retry=2, timeout_sec=1.0),
    )
    action = {"task_id": "t1", "drones": {"d1": {"offset": [1, 0]}}}

    with patch.object(
        bridge,
        "_dispatch_once",
        new_callable=AsyncMock,
        side_effect=[
            {"status": "error"},
            {"status": "error"},
            {"status": "ok", "applied": {}},
        ],
    ) as mock_once:
        with patch(
            "app.modules.realtime.manager.realtime_manager.persist_task_data"
        ) as mock_persist:
            ack = await bridge.dispatch_action(action, cfg)

    assert ack["status"] == "ok"
    assert mock_once.await_count == 3
    mock_persist.assert_called_once()


@pytest.mark.asyncio
async def test_dispatch_action_batched_calls_per_agent():
    bridge = RealtimeEngineBridge()
    cfg = InteractionConfig(
        bridge="realtime",
        action=ActionConfig(dispatch_mode="batched", require_ack=False),
    )
    action = {
        "task_id": "t1",
        "agents": {"uav": {"offset": [1, 0]}, "ugv": {"offset": [0, 1]}},
    }
    ws = MagicMock()

    with patch(
        "app.modules.realtime.manager.realtime_manager.resolve_lj_engine_targets",
        return_value=[ws],
    ):
        with patch(
            "app.modules.realtime.manager.realtime_manager.send_command_to_engine",
            new_callable=AsyncMock,
        ) as mock_send:
            with patch(
                "app.modules.realtime.manager.realtime_manager.persist_task_data"
            ):
                ack = await bridge.dispatch_action(action, cfg)

    assert ack["batched"] is True
    assert ack["batch_count"] == 2
    assert mock_send.await_count == 2
    first_message = mock_send.await_args_list[0].args[0]
    assert first_message["action"]["agent"] == "uav"


@pytest.mark.asyncio
async def test_base_env_step_honors_step_interval_sec():
    from app.modules.envs.envs.open_vocab_nav_env import OpenVocabNavEnv
    from app.modules.envs.evaluators import build_evaluator

    spec = ScenarioSpec.from_file(
        __import__("pathlib").Path(__file__).resolve().parents[1]
        / "app/modules/envs/scenarios/open_vocab_navigation.json"
    )
    env = OpenVocabNavEnv()
    env.evaluator = build_evaluator(spec.evaluator)
    env.interaction = InteractionConfig(bridge="mock", step_interval_sec=0.05)

    await env.reset(spec)

    with patch("app.modules.envs.base.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        await env.step({"offset": [1.0, 0.0], "speed": 10})

    mock_sleep.assert_awaited_once_with(0.05)
