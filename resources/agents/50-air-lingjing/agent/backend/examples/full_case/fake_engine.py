"""\u6d4b\u8bd5\u7528 fake LJ-ENGINE WebSocket \u5ba2\u6237\u7aef.

\u53ea\u6709\u5f53\u4f60\u60f3\u8dd1 ``UEMultiDroneBridge`` (\u8d70\u771f\u5b9e WebSocket) \u53c8\u6ca1\u6709 UE
\u5de5\u7a0b\u7684\u65f6\u5019\u624d\u7528\u5230\u5b83 \u2014 Mock \u6a21\u5f0f\u4e0b\u5b8c\u5168\u7528\u4e0d\u4e0a.

\u6ce8\u610f: \u8fd9\u662f *\u5ba2\u6237\u7aef* \u2014 \u5b83\u8fde\u5230\u672c\u670d\u52a1\u7684 ``/ws/LJ-ENGINE/...``, \u626e\u6f14 UE \u5f15\u64ce\u7684\u89d2\u8272.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from examples.full_case.scenario import delivery_parcels, delivery_targets, fleet_names


class FakeUEFleet:
    """\u6a21\u62df\u771f\u5b9e LJ-ENGINE \u5bf9 ``resetDeliveryScenario / getFleetObservation /
    dispatchFleetAction`` \u7684\u5e94\u7b54, \u8ba9\u4f60\u5728\u4e0d\u5f00 UE \u7684\u60c5\u51b5\u4e0b\u8dd1\u901a\u771f\u5b9e WS \u8def\u5f84."""

    def __init__(self, ws_url: str) -> None:
        self.ws_url = ws_url
        self.fleet = fleet_names()
        self.targets = delivery_targets()
        self.parcels = delivery_parcels()
        self.poses: dict[str, dict[str, float]] = {}
        self.delivered: dict[str, bool] = {n: False for n in self.fleet}
        self.connected = asyncio.Event()
        self.received: list[dict[str, Any]] = []
        self._task: asyncio.Task | None = None

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

                if command_type == "resetDeliveryScenario":
                    scenario = data.get("scenario") or {}
                    drones = (scenario.get("equipmentList") or {}).get("droneEntityList") or []
                    for d in drones:
                        pos = d.get("data") or {}
                        self.poses[d.get("name")] = {
                            "x": float(pos.get("X", 0)),
                            "y": float(pos.get("Y", 0)),
                            "z": float(pos.get("Z", 60)),
                        }
                    self.delivered = {n: False for n in self.fleet}
                    await ws.send(json.dumps({
                        "commandType": "sceneResetAck",
                        "request_id": request_id,
                        "data": {"status": "reset", "fleet": self.fleet},
                    }))

                elif command_type == "getFleetObservation":
                    drones_obs: dict[str, Any] = {}
                    for name in self.fleet:
                        pose = self.poses.get(name) or {"x": 0.0, "y": 0.0, "z": 60.0}
                        tgt = self.targets[name]
                        distance = ((tgt["x"] - pose["x"]) ** 2 + (tgt["y"] - pose["y"]) ** 2) ** 0.5
                        drones_obs[name] = {
                            "pose": dict(pose),
                            "delivery_target": dict(tgt),
                            "parcel": self.parcels.get(name, "package"),
                            "distance": distance,
                            "delivered": self.delivered[name],
                            "camera_rgb": "",
                        }
                    await ws.send(json.dumps({
                        "commandType": "observationResponse",
                        "request_id": request_id,
                        "data": {
                            "drones": drones_obs,
                            "delivery_targets": dict(self.targets),
                            "all_delivered": all(self.delivered.values()),
                        },
                    }))

                elif command_type == "dispatchFleetAction":
                    action = data.get("action") or {}
                    drones_cmd = action.get("drones") or {}
                    for name, cmd in drones_cmd.items():
                        if self.delivered.get(name):
                            continue
                        offset = cmd.get("offset") or [0, 0]
                        dx = float(offset[0]) if len(offset) > 0 else 0.0
                        dy = float(offset[1]) if len(offset) > 1 else 0.0
                        pose = self.poses.setdefault(name, {"x": 0.0, "y": 0.0, "z": 60.0})
                        pose["x"] += dx
                        pose["y"] += dy
                        tgt = self.targets.get(name)
                        if tgt:
                            distance = ((tgt["x"] - pose["x"]) ** 2 + (tgt["y"] - pose["y"]) ** 2) ** 0.5
                            if distance <= 5.0:
                                self.delivered[name] = True
                    if request_id:
                        await ws.send(json.dumps({
                            "commandType": "actionAck",
                            "request_id": request_id,
                            "data": {"status": "ok", "delivered": dict(self.delivered)},
                        }))

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
