"""LJ-ENGINE WebSocket \u5ba2\u6237\u7aef\u53c2\u8003\u5b9e\u73b0 \u2014 \u4f9b UE / \u4eff\u771f\u5f15\u64ce\u8054\u8c03 python-lingjing-ai-server.

\u672c\u6a21\u5757\u6a21\u62df UE \u4fa7\u9700\u8981\u5b9e\u73b0\u7684\u534f\u8bae:

1. \u8fde\u63a5 ``/ws/LJ-ENGINE/{address}``\uff0c\u8bfb\u53d6 SYSTEM \u6b22\u8fce\u6d88\u606f\u3002
2. \u63a5\u6536\u670d\u52a1\u7aef ``{"type":"COMMAND","data":{...}}``\uff0c\u5176\u4e2d ``data`` \u542b ``commandType``\u3002
3. **\u83b7\u53d6\u60f3\u5b9a**: \u5904\u7406 ``reset*Scenario``\uff0c\u89e3\u6790 ``data.scenario`` (sceneName / equipmentList / taskMatrix)\u3002
4. **\u63a5\u6536\u667a\u80fd\u4f53\u6307\u4ee4**: \u5904\u7406 ``dispatch*Action`` / ``executeAction``\uff0c\u5728 UE \u91cc\u5e94\u7528\u52a8\u4f5c\u3002
5. **\u56de\u4f20\u73af\u5883\u72b6\u6001**: \u5bf9\u5e26 ``request_id`` \u7684\u8bf7\u6c42\u56de\u5305 (\u4efb\u610f ``commandType`` \u5747\u53ef\uff0c\u6309 id \u5339\u914d)\u3002
6. **\u4e3b\u52a8\u4e0a\u62a5\u9065\u6d4b** (\u53ef\u9009): \u53d1\u9001 ``pushEngineTelemetry``\uff0c\u670d\u52a1\u7aef\u6309 ``taskId`` \u5199\u5165 ``sim_data``\u3002

\u5728 Unreal \u91cc\u7528 WebSocket \u63d2\u4ef6\u6309\u540c\u6837 JSON \u5b57\u6bb5\u5b9e\u73b0\u5373\u53ef; \u672c\u6587\u4ef6\u7528 Python \u4fbf\u4e8e\u5148\u8dd1\u901a\u94fe\u8def\u3002
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
from dataclasses import dataclass, field
from typing import Any, Callable

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
PROFILE_COMMANDS: dict[str, dict[str, str]] = {
    "open_vocab": {
        "reset": "resetScenario",
        "observe": "getObservation",
        "action": "executeAction",
        "reset_ack": "sceneResetAck",
        "observe_ack": "observationResponse",
        "action_ack": "actionAck",
    },
    "delivery": {
        "reset": "resetDeliveryScenario",
        "observe": "getFleetObservation",
        "action": "dispatchFleetAction",
        "reset_ack": "sceneResetAck",
        "observe_ack": "observationResponse",
        "action_ack": "actionAck",
    },
    "fire_rescue": {
        "reset": "resetFireRescueScenario",
        "observe": "getFireRescueObservation",
        "action": "dispatchFireRescueAction",
        "reset_ack": "fireRescueResetAck",
        "observe_ack": "fireRescueObservationResponse",
        "action_ack": "fireRescueActionAck",
    },
}


def _parse_offset(offset: Any) -> tuple[float, float]:
    if isinstance(offset, (list, tuple)) and len(offset) >= 2:
        return float(offset[0]), float(offset[1])
    if isinstance(offset, dict):
        return float(offset.get("x", 0)), float(offset.get("y", 0))
    return 0.0, 0.0


@dataclass
class EngineWorldState:
    """\u8fdb\u7a0b\u5185\u6781\u7b80\u4e16\u754c\u6a21\u578b \u2014 UE \u5de5\u7a0b\u91cc\u7528\u771f\u5b9e Actor \u72b6\u6001\u66ff\u6362\u5373\u53ef."""

    task_id: str = ""
    scenario: dict[str, Any] = field(default_factory=dict)
    poses: dict[str, dict[str, float]] = field(default_factory=dict)
    fires: dict[str, dict[str, Any]] = field(default_factory=dict)
    delivered: dict[str, bool] = field(default_factory=dict)
    step: int = 0
    profile: str = "delivery"

    def load_scenario(self, scenario: dict[str, Any], profile: str) -> None:
        self.scenario = scenario
        self.profile = profile
        self.task_id = str(scenario.get("taskId") or "")
        self.poses.clear()
        self.delivered.clear()
        self.fires.clear()
        equipment = scenario.get("equipmentList") or {}
        for d in equipment.get("droneEntityList") or []:
            pos = d.get("data") or {}
            name = str(d.get("name") or d.get("equipmentCode"))
            self.poses[name] = {
                "x": float(pos.get("X", pos.get("x", 0))),
                "y": float(pos.get("Y", pos.get("y", 0))),
                "z": float(pos.get("Z", pos.get("z", 60))),
            }
            self.delivered[name] = False
        for v in equipment.get("autoVehicleEntityList") or []:
            pos = v.get("data") or {}
            name = str(v.get("name") or v.get("equipmentCode"))
            self.poses[name] = {
                "x": float(pos.get("X", pos.get("x", 0))),
                "y": float(pos.get("Y", pos.get("y", 0))),
                "z": float(pos.get("Z", pos.get("z", 0))),
            }
        for item in scenario.get("taskMatrix") or []:
            spots = (item.get("initial_state") or {}).get("fire_spots")
            if spots:
                for idx, spot in enumerate(spots):
                    fid = str(spot.get("id") or f"fire-{idx + 1:02d}")
                    self.fires[fid] = {
                        "id": fid,
                        "position": {
                            "x": float(spot.get("x", 0)),
                            "y": float(spot.get("y", 0)),
                            "z": float(spot.get("z", 0)),
                        },
                        "status": "active",
                        "progress": 0,
                    }

    def build_observation(self, query: dict[str, Any] | None = None) -> dict[str, Any]:
        query = query or {}
        if self.profile == "fire_rescue":
            obs = self._obs_fire_rescue()
        elif self.profile == "open_vocab":
            obs = self._obs_open_vocab()
        else:
            obs = self._obs_delivery()
        return self._apply_observation_contract(obs, query)

    def _obs_open_vocab(self) -> dict[str, Any]:
        pose = next(iter(self.poses.values()), {"x": 0, "y": 0, "z": 50})
        goal = {"x": 80.0, "y": 0.0, "z": 50.0}
        for item in self.scenario.get("taskMatrix") or []:
            gp = (item.get("initial_state") or {}).get("goalPosition") or {}
            goal = {
                "x": float(gp.get("lon", gp.get("x", 80))),
                "y": float(gp.get("lat", gp.get("y", 0))),
                "z": float(gp.get("alt", gp.get("z", 50))),
            }
            break
        dist = math.hypot(goal["x"] - pose["x"], goal["y"] - pose["y"])
        return {
            "pose": dict(pose),
            "goal_position": goal,
            "distance": dist,
            "camera_rgb": "",
            "step": self.step,
        }

    def _obs_delivery(self) -> dict[str, Any]:
        drones_obs: dict[str, Any] = {}
        for name, pose in self.poses.items():
            drones_obs[name] = {
                "pose": dict(pose),
                "delivered": bool(self.delivered.get(name)),
                "camera_rgb": "",
            }
        return {
            "drones": drones_obs,
            "step": self.step,
            "all_delivered": bool(self.delivered) and all(self.delivered.values()),
        }

    def _obs_fire_rescue(self) -> dict[str, Any]:
        uav = next(
            (n for n in self.poses if "drone" in n.lower() or "uav" in n.lower()),
            next(iter(self.poses), "drone1"),
        )
        uav_pose = self.poses.get(uav) or {"x": 0, "y": 0, "z": 80}
        visible = []
        for fid, fire in self.fires.items():
            if fire["status"] == "extinguished":
                continue
            p = fire["position"]
            d = math.hypot(p["x"] - uav_pose["x"], p["y"] - uav_pose["y"])
            if d <= 60.0:
                visible.append({"id": fid, "position": p, "distance_from_uav": d, "status": fire["status"]})
        agents_obs = {
            uav: {"pose": dict(uav_pose), "fov_radius": 60.0, "visible_fires": visible, "camera_rgb": ""},
        }
        for name, pose in self.poses.items():
            if name == uav:
                continue
            agents_obs[name] = {"pose": dict(pose), "camera_rgb": ""}
        fires_summary = [
            {"id": fid, "position": f["position"], "status": f["status"], "progress": f.get("progress", 0)}
            for fid, f in self.fires.items()
        ]
        return {
            "agents": agents_obs,
            "fires": fires_summary,
            "step": self.step,
            "all_extinguished": bool(self.fires)
            and all(f["status"] == "extinguished" for f in self.fires.values()),
        }

    @staticmethod
    def _apply_observation_contract(obs: dict[str, Any], query: dict[str, Any]) -> dict[str, Any]:
        """Best-effort filter: keep only top-level keys listed in observation_schema.spaces."""

        schema = query.get("observation_schema") or query.get("observationSchema")
        if not isinstance(schema, dict):
            return obs
        spaces = schema.get("spaces")
        if not isinstance(spaces, dict) or not spaces:
            return obs
        return {key: value for key, value in obs.items() if key in spaces}

    def apply_action(self, action: dict[str, Any]) -> dict[str, Any]:
        self.step += 1
        if self.profile == "fire_rescue":
            return self._apply_fire(action)
        if self.profile == "open_vocab":
            return self._apply_open_vocab(action)
        return self._apply_delivery(action)

    def _apply_open_vocab(self, action: dict[str, Any]) -> dict[str, Any]:
        name = next(iter(self.poses), "drone1")
        dx, dy = _parse_offset(action.get("offset"))
        pose = self.poses.setdefault(name, {"x": 0, "y": 0, "z": 50})
        pose["x"] += dx
        pose["y"] += dy
        return {"status": "ok", "pose": dict(pose)}

    def _apply_delivery(self, action: dict[str, Any]) -> dict[str, Any]:
        for name, cmd in (action.get("drones") or {}).items():
            if self.delivered.get(name):
                continue
            dx, dy = _parse_offset(cmd.get("offset"))
            pose = self.poses.setdefault(name, {"x": 0, "y": 0, "z": 60})
            pose["x"] += dx
            pose["y"] += dy
            if math.hypot(pose["x"], pose["y"]) >= 50:
                self.delivered[name] = True
        return {"status": "ok", "delivered": dict(self.delivered)}

    def _apply_fire(self, action: dict[str, Any]) -> dict[str, Any]:
        for name, cmd in (action.get("agents") or {}).items():
            dx, dy = _parse_offset(cmd.get("offset"))
            pose = self.poses.setdefault(name, {"x": 0, "y": 0, "z": 0})
            pose["x"] += dx
            pose["y"] += dy
            if str(cmd.get("action_type")) == "extinguish":
                tid = cmd.get("target_id")
                if tid and tid in self.fires:
                    fire = self.fires[tid]
                    d = math.hypot(fire["position"]["x"] - pose["x"], fire["position"]["y"] - pose["y"])
                    if d <= 8.0:
                        fire["progress"] = int(fire.get("progress", 0)) + 1
                        fire["status"] = "in_progress"
                        if fire["progress"] >= 3:
                            fire["status"] = "extinguished"
        return {
            "status": "ok",
            "fires": {fid: f["status"] for fid, f in self.fires.items()},
        }


class LJEngineClient:
    """UE \u4eff\u771f\u5f15\u64ce WebSocket \u5ba2\u6237\u7aef (LJ-ENGINE \u89d2\u8272)."""

    def __init__(
        self,
        ws_url: str,
        *,
        profile: str = "delivery",
        on_command: Callable[[str, dict[str, Any]], None] | None = None,
        telemetry_interval_sec: float = 0.0,
    ) -> None:
        self.ws_url = ws_url
        self.profile = profile
        self.commands = PROFILE_COMMANDS[profile]
        self.world = EngineWorldState(profile=profile)
        self.on_command = on_command
        self.telemetry_interval_sec = telemetry_interval_sec
        self.connected = asyncio.Event()
        self._ws: Any = None
        self._task: asyncio.Task | None = None
        self._telemetry_task: asyncio.Task | None = None

    async def _reply(self, request_id: str | None, command_type: str, data: dict[str, Any]) -> None:
        if not request_id or self._ws is None:
            return
        await self._ws.send(
            json.dumps(
                {"commandType": command_type, "request_id": request_id, "requestId": request_id, "data": data},
                ensure_ascii=False,
            )
        )

    async def push_telemetry(self, payload: dict[str, Any] | None = None) -> None:
        """\u4e3b\u52a8\u5411\u670d\u52a1\u7aef\u63a8\u9001\u4e00\u5e27\u5b9e\u65f6\u4eff\u771f\u6570\u636e (\u5199\u5165 sim_data, phase=telemetry)."""

        if self._ws is None:
            return
        body = payload if payload is not None else self.world.build_observation()
        await self._ws.send(
            json.dumps(
                {
                    "commandType": "pushEngineTelemetry",
                    "taskId": self.world.task_id,
                    "task_id": self.world.task_id,
                    "data": body,
                },
                ensure_ascii=False,
            )
        )

    async def subscribe_scene(self, task_id: str) -> None:
        """\u8ba2\u9605 task_id \u2014 unicast \u6a21\u5f0f\u4e0b\u670d\u52a1\u7aef\u4f1a\u628a RPC \u53d1\u5230\u5df2\u8ba2\u9605\u7684\u5f15\u64ce\u4f1a\u8bdd."""

        if self._ws is None:
            return
        await self._ws.send(
            json.dumps(
                {
                    "commandType": "subscribeScene",
                    "command": {"taskId": task_id},
                }
            )
        )

    async def _handle_command(self, data: dict[str, Any]) -> None:
        command_type = data.get("commandType")
        request_id = data.get("request_id") or data.get("requestId")
        if self.on_command:
            self.on_command(command_type, data)

        cmds = self.commands
        if command_type == cmds["reset"]:
            scenario = data.get("scenario") or {}
            self.world.load_scenario(scenario, self.profile)
            logger.info("\u6536\u5230\u60f3\u5b9a reset: scene=%s taskId=%s", scenario.get("sceneName"), self.world.task_id)
            await self._reply(
                request_id,
                cmds["reset_ack"],
                {"status": "reset", "taskId": self.world.task_id, "agents": list(self.world.poses)},
            )
            if self.world.task_id:
                await self.subscribe_scene(self.world.task_id)
            return

        if command_type == cmds["observe"]:
            query = data.get("query") or {}
            modalities = query.get("modalities") or []
            schema = query.get("observation_schema") or query.get("observationSchema")
            if modalities or schema:
                logger.info(
                    "\u89c2\u6d4b\u8bf7\u6c42 modalities=%s schema_keys=%s",
                    modalities,
                    list((schema or {}).get("spaces", schema or {}).keys())
                    if isinstance(schema, dict)
                    else None,
                )
            obs = self.world.build_observation(query=query)
            await self._reply(request_id, cmds["observe_ack"], obs)
            return

        if command_type == cmds["action"]:
            action = data.get("action") or {}
            result = self.world.apply_action(action)
            await self._reply(request_id, cmds["action_ack"], result)
            return

        logger.debug("\u672a\u5904\u7406\u7684 commandType=%s", command_type)

    async def _recv_loop(self) -> None:
        import websockets

        async with websockets.connect(self.ws_url) as ws:
            self._ws = ws
            welcome = await ws.recv()
            logger.info("SYSTEM: %s", welcome)
            self.connected.set()

            if self.telemetry_interval_sec > 0:
                self._telemetry_task = asyncio.create_task(self._telemetry_loop())

            while True:
                raw = await ws.recv()
                envelope = json.loads(raw)
                msg_type = envelope.get("type")
                payload = envelope.get("data") or {}
                if isinstance(payload, list):
                    payload = payload[0] if payload else {}

                if msg_type == "COMMAND" and isinstance(payload, dict):
                    await self._handle_command(payload)
                elif msg_type == "DATA":
                    logger.info("\u6536\u5230 DATA \u4e0b\u884c (\u53ef\u8f6c\u7ed9 UE \u84dd\u56fe): %s", payload)
                else:
                    logger.debug("\u5176\u5b83\u6d88\u606f type=%s", msg_type)

    async def _telemetry_loop(self) -> None:
        while self.connected.is_set():
            if self.world.task_id:
                try:
                    await self.push_telemetry()
                except Exception:  # noqa: BLE001
                    logger.exception("pushEngineTelemetry failed")
            await asyncio.sleep(self.telemetry_interval_sec)

    async def start(self) -> None:
        self._task = asyncio.create_task(self._recv_loop())
        await asyncio.wait_for(self.connected.wait(), timeout=10.0)

    async def stop(self) -> None:
        if self._telemetry_task:
            self._telemetry_task.cancel()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except BaseException:
                pass


async def main() -> None:
    parser = argparse.ArgumentParser(description="LJ-ENGINE UE \u5ba2\u6237\u7aef\u53c2\u8003\u5b9e\u73b0")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=9909)
    parser.add_argument("--address", default="ue-engine-01", help="\u5bf9\u5e94 /ws/LJ-ENGINE/{address}")
    parser.add_argument(
        "--profile",
        choices=list(PROFILE_COMMANDS),
        default="delivery",
        help="\u4e1a\u52a1 profile, \u51b3\u5b9a\u8bc6\u522b\u7684 reset/observe/action commandType",
    )
    parser.add_argument(
        "--telemetry-interval",
        type=float,
        default=0.0,
        help=">0 \u65f6\u5468\u671f\u6027 pushEngineTelemetry (\u79d2)",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    url = f"ws://{args.host}:{args.port}/ws/LJ-ENGINE/{args.address}"
    client = LJEngineClient(
        url,
        profile=args.profile,
        telemetry_interval_sec=args.telemetry_interval,
        on_command=lambda cmd, _: logger.info("\u2190 COMMAND %s", cmd),
    )
    print(f"\u8fde\u63a5 {url} (profile={args.profile})\uff0c\u7b49\u5f85\u670d\u52a1\u7aef\u4e0b\u53d1\u60f3\u5b9a/\u89c2\u6d4b/\u52a8\u4f5c\u2026")
    print("\u53e6\u5f00\u7ec8\u7aef\u8dd1: python -m examples.full_case.run_case --realtime")
    await client.start()
    try:
        await asyncio.Future()
    except asyncio.CancelledError:
        pass


if __name__ == "__main__":
    asyncio.run(main())
