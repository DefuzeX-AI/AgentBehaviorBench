"""\u6d4b\u8bd5\u7528 fake LJ-ENGINE WebSocket \u5ba2\u6237\u7aef (\u706d\u706b case \u4e13\u7528).

\u4ec5\u5f53\u8dd1 ``UEFireRescueBridge`` (\u8d70\u771f\u5b9e WebSocket) \u53c8\u6ca1\u6709 UE \u5de5\u7a0b\u65f6\u624d\u7528 \u2014
Mock \u6a21\u5f0f\u5b8c\u5168\u7528\u4e0d\u4e0a.

\u6ce8\u610f: \u8fd9\u662f *\u5ba2\u6237\u7aef*, \u5b83\u8fde\u5230\u672c\u670d\u52a1\u7684 ``/ws/LJ-ENGINE/...`` \u626e\u6f14 UE \u5f15\u64ce\u7684\u89d2\u8272.
"""

from __future__ import annotations

import asyncio
import json
import math
from typing import Any

from examples.fire_rescue.scenario import fire_spot_table, uav_name, ugv_names


class FakeUEFireWorld:
    """\u6a21\u62df ``resetFireRescueScenario / getFireRescueObservation /
    dispatchFireRescueAction`` \u4e09\u6761\u547d\u4ee4\u7684\u5e94\u7b54."""

    def __init__(
        self,
        ws_url: str,
        *,
        fov_radius: float = 60.0,
        extinguish_distance: float = 8.0,
        extinguish_steps_required: int = 3,
    ) -> None:
        self.ws_url = ws_url
        self.uav = uav_name()
        self.ugvs = ugv_names()
        self.fov_radius = float(fov_radius)
        self.extinguish_distance = float(extinguish_distance)
        self.extinguish_steps_required = int(extinguish_steps_required)
        self.poses: dict[str, dict[str, float]] = {}
        self.fires: dict[str, dict[str, Any]] = {}
        self.connected = asyncio.Event()
        self.received: list[dict[str, Any]] = []
        self._task: asyncio.Task | None = None

    def _reset_fires(self, spots: list[dict[str, Any]] | None = None) -> None:
        spots = spots or fire_spot_table()
        self.fires = {}
        for idx, spot in enumerate(spots):
            fid = str(spot.get("id") or f"fire-{idx + 1:02d}")
            self.fires[fid] = {
                "id": fid,
                "position": {
                    "x": float(spot.get("x", 0)),
                    "y": float(spot.get("y", 0)),
                    "z": float(spot.get("z", 0)),
                },
                "intensity": float(spot.get("intensity", 1.0)),
                "status": "active",
                "progress": 0,
                "active_extinguisher": None,
            }

    def _visible(self) -> list[dict[str, Any]]:
        uav_pose = self.poses.get(self.uav) or {"x": 0.0, "y": 0.0, "z": 80.0}
        out: list[dict[str, Any]] = []
        for fid, fire in self.fires.items():
            if fire["status"] == "extinguished":
                continue
            d = math.hypot(
                fire["position"]["x"] - uav_pose["x"],
                fire["position"]["y"] - uav_pose["y"],
            )
            if d <= self.fov_radius:
                out.append(
                    {
                        "id": fid,
                        "position": dict(fire["position"]),
                        "distance_from_uav": d,
                        "intensity": fire["intensity"],
                        "status": fire["status"],
                    }
                )
        return out

    def _parse_offset(self, offset: Any) -> tuple[float, float]:
        if isinstance(offset, (list, tuple)) and len(offset) >= 2:
            return float(offset[0]), float(offset[1])
        if isinstance(offset, dict):
            return float(offset.get("x", 0)), float(offset.get("y", 0))
        return 0.0, 0.0

    async def _run(self) -> None:
        import websockets

        async with websockets.connect(self.ws_url) as ws:
            await ws.recv()
            self.connected.set()
            while True:
                raw = await ws.recv()
                envelope = json.loads(raw)
                data = envelope.get("data") or {}
                if isinstance(data, list):
                    data = data[0] if data else {}
                command_type = data.get("commandType")
                request_id = data.get("request_id") or data.get("requestId")
                self.received.append({"commandType": command_type})

                if command_type == "resetFireRescueScenario":
                    scenario = data.get("scenario") or {}
                    equipment = scenario.get("equipmentList") or {}
                    self.poses = {}
                    for d in equipment.get("droneEntityList") or []:
                        pos = d.get("data") or {}
                        self.poses[d.get("name")] = {
                            "x": float(pos.get("X", 0)),
                            "y": float(pos.get("Y", 0)),
                            "z": float(pos.get("Z", 80)),
                        }
                    for v in equipment.get("autoVehicleEntityList") or []:
                        pos = v.get("data") or {}
                        self.poses[v.get("name")] = {
                            "x": float(pos.get("X", 0)),
                            "y": float(pos.get("Y", 0)),
                            "z": float(pos.get("Z", 0)),
                        }
                    fires_raw: list[dict[str, Any]] = []
                    for item in scenario.get("taskMatrix") or []:
                        spots = (item.get("initial_state") or {}).get("fire_spots")
                        if spots:
                            fires_raw = list(spots)
                            break
                    self._reset_fires(fires_raw)
                    await ws.send(
                        json.dumps(
                            {
                                "commandType": "fireRescueResetAck",
                                "request_id": request_id,
                                "data": {
                                    "status": "reset",
                                    "fire_total": len(self.fires),
                                    "agents": list(self.poses),
                                },
                            }
                        )
                    )

                elif command_type == "getFireRescueObservation":
                    agents_obs: dict[str, Any] = {}
                    uav_pose = self.poses.get(self.uav) or {"x": 0.0, "y": 0.0, "z": 80.0}
                    agents_obs[self.uav] = {
                        "pose": dict(uav_pose),
                        "fov_radius": self.fov_radius,
                        "visible_fires": self._visible(),
                        "camera_rgb": "",
                    }
                    for ugv in self.ugvs:
                        pose = self.poses.get(ugv) or {"x": 0.0, "y": 0.0, "z": 0.0}
                        agents_obs[ugv] = {
                            "pose": dict(pose),
                            "extinguish_distance": self.extinguish_distance,
                            "extinguishing_fires": [
                                fid
                                for fid, f in self.fires.items()
                                if f.get("active_extinguisher") == ugv
                                and f["status"] == "in_progress"
                            ],
                            "extinguished_fires": [
                                fid
                                for fid, f in self.fires.items()
                                if f["status"] == "extinguished"
                            ],
                            "camera_rgb": "",
                        }
                    fires_summary = [
                        {
                            "id": fid,
                            "position": dict(f["position"]),
                            "status": f["status"],
                            "progress": int(f["progress"]),
                        }
                        for fid, f in self.fires.items()
                    ]
                    await ws.send(
                        json.dumps(
                            {
                                "commandType": "fireRescueObservationResponse",
                                "request_id": request_id,
                                "data": {
                                    "agents": agents_obs,
                                    "fires": fires_summary,
                                    "all_extinguished": bool(self.fires)
                                    and all(
                                        f["status"] == "extinguished"
                                        for f in self.fires.values()
                                    ),
                                },
                            }
                        )
                    )

                elif command_type == "dispatchFireRescueAction":
                    action = data.get("action") or {}
                    agents_cmd = action.get("agents") or {}

                    uav_cmd = agents_cmd.get(self.uav) or {}
                    dx, dy = self._parse_offset(uav_cmd.get("offset"))
                    alt_delta = float(uav_cmd.get("altitude_delta", 0.0))
                    pose = self.poses.setdefault(self.uav, {"x": 0.0, "y": 0.0, "z": 80.0})
                    pose["x"] += dx
                    pose["y"] += dy
                    pose["z"] = max(20.0, pose["z"] + alt_delta)

                    for ugv in self.ugvs:
                        cmd = agents_cmd.get(ugv) or {}
                        dx, dy = self._parse_offset(cmd.get("offset"))
                        pose = self.poses.setdefault(ugv, {"x": 0.0, "y": 0.0, "z": 0.0})
                        pose["x"] += dx
                        pose["y"] += dy
                        target_id = cmd.get("target_id")
                        action_type = str(cmd.get("action_type", "idle"))
                        if (
                            action_type == "extinguish"
                            and target_id
                            and target_id in self.fires
                            and self.fires[target_id]["status"] != "extinguished"
                        ):
                            fire = self.fires[target_id]
                            d = math.hypot(
                                fire["position"]["x"] - pose["x"],
                                fire["position"]["y"] - pose["y"],
                            )
                            if d <= self.extinguish_distance:
                                fire["status"] = "in_progress"
                                fire["progress"] = int(fire["progress"]) + 1
                                fire["active_extinguisher"] = ugv
                                if fire["progress"] >= self.extinguish_steps_required:
                                    fire["status"] = "extinguished"
                                    fire["active_extinguisher"] = None

                    if request_id:
                        await ws.send(
                            json.dumps(
                                {
                                    "commandType": "fireRescueActionAck",
                                    "request_id": request_id,
                                    "data": {
                                        "status": "ok",
                                        "fires": {
                                            fid: f["status"] for fid, f in self.fires.items()
                                        },
                                    },
                                }
                            )
                        )

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        await asyncio.wait_for(self.connected.wait(), timeout=5.0)

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except BaseException:
                pass
