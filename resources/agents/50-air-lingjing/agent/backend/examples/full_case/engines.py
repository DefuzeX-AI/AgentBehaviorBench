"""\u591a\u673a\u914d\u9001\u4efb\u52a1\u7684 EngineBridge \u5b9e\u73b0.

\u63d0\u4f9b\u4e24\u79cd\u5f15\u64ce\u63a5\u5165:

* :class:`MockMultiDroneBridge` \u2014 \u5168\u8fdb\u7a0b\u5185\u7684\u4eff\u771f\u4e16\u754c. \u7528\u6237\u6ca1\u6709 UE \u4e5f\u80fd\u8dd1\u901a,
  \u9002\u5408\u5199\u5355\u6d4b / \u8c03\u8bd5 policy.
* :class:`UEMultiDroneBridge` \u2014 \u76f4\u63a5\u590d\u7528 :class:`RealtimeEngineBridge`,
  \u901a\u8fc7\u9879\u76ee\u91cc\u73b0\u6210\u7684 :data:`app.modules.realtime.manager.realtime_manager`
  \u628a reset / observation / action \u901a\u8fc7 WebSocket \u53d1\u7ed9\u771f\u5b9e LJ-ENGINE.
  \u7528\u6237\u4e0d\u518d\u9700\u8981\u624b\u52a8\u62fc ``request_to_engine`` \u8c03\u7528 \u2014 \u62ff\u5230 bridge \u5b9e\u4f8b\u76f4\u63a5\u7ed9
  env \u7528\u5373\u53ef.
"""

from __future__ import annotations

from typing import Any

from app.modules.envs.engine_bridge.realtime_bridge import RealtimeEngineBridge
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

from examples.full_case.scenario import delivery_parcels, delivery_targets, fleet_names


class MockMultiDroneBridge:
    """\u8fdb\u7a0b\u5185\u7684\u7b80\u6613\u591a\u673a\u4e16\u754c\u6a21\u578b, \u7528\u4e8e\u79bb\u7ebf\u5f00\u53d1."""

    def __init__(self) -> None:
        self.fleet = fleet_names()
        self.targets = delivery_targets()
        self.parcels = delivery_parcels()
        self.poses: dict[str, dict[str, float]] = {}
        self.delivered: dict[str, bool] = {n: False for n in self.fleet}
        self._step = 0

    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]:
        self._step = 0
        self.delivered = {n: False for n in self.fleet}
        self.poses = {}
        for asset in spec.assets:
            pos = asset.position
            self.poses[asset.name] = {
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "z": float(pos.get("z", pos.get("alt", 60))),
            }
        return {
            "status": "reset",
            "fleet": self.fleet,
            "targets": self.targets,
            "parcels": self.parcels,
        }

    async def request_observation(
        self, query: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        drones_obs: dict[str, Any] = {}
        for name in self.fleet:
            pose = self.poses.get(name) or {"x": 0.0, "y": 0.0, "z": 60.0}
            tgt = self.targets[name]
            dx = tgt["x"] - pose["x"]
            dy = tgt["y"] - pose["y"]
            distance = (dx * dx + dy * dy) ** 0.5
            drones_obs[name] = {
                "pose": dict(pose),
                "delivery_target": dict(tgt),
                "parcel": self.parcels.get(name, "package"),
                "distance": distance,
                "delivered": bool(self.delivered[name]),
                "camera_rgb": "",
            }
        return {
            "drones": drones_obs,
            "delivery_targets": dict(self.targets),
            "step": self._step,
            "all_delivered": all(self.delivered.values()),
        }

    async def dispatch_action(self, action: dict[str, Any], cfg: InteractionConfig) -> dict[str, Any]:
        drones_cmd = action.get("drones") or {}
        applied: dict[str, dict[str, float]] = {}
        for name in self.fleet:
            if self.delivered[name]:
                continue
            cmd = drones_cmd.get(name) or {}
            offset = cmd.get("offset")
            if isinstance(offset, (list, tuple)) and len(offset) >= 2:
                dx, dy = float(offset[0]), float(offset[1])
            elif isinstance(offset, dict):
                dx, dy = float(offset.get("x", 0)), float(offset.get("y", 0))
            else:
                dx, dy = 0.0, 0.0
            pose = self.poses.setdefault(name, {"x": 0.0, "y": 0.0, "z": 60.0})
            pose["x"] += dx
            pose["y"] += dy
            applied[name] = {"dx": dx, "dy": dy}
            tgt = self.targets[name]
            distance = ((tgt["x"] - pose["x"]) ** 2 + (tgt["y"] - pose["y"]) ** 2) ** 0.5
            if distance <= 5.0:
                self.delivered[name] = True
        self._step += 1
        return {"status": "ok", "applied": applied, "delivered": dict(self.delivered)}

    async def call_custom(
        self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        return {"status": "noop", "command": command_name}

    async def close(self) -> None:
        return None


class UEMultiDroneBridge(RealtimeEngineBridge):
    """\u771f\u5b9e UE \u5f15\u64ce\u6865, \u76f4\u63a5\u7ee7\u627f RealtimeEngineBridge.

    \u7528\u6237\u5f97\u5230\u4e00\u4e2a\u672c\u7c7b\u5b9e\u4f8b\u5c31\u80fd\u8ba9 env \u628a\u573a\u666f / \u89c2\u6d4b / \u52a8\u4f5c\u901a\u8fc7
    ``realtime_manager.request_to_engine`` \u63a8\u7ed9 LJ-ENGINE \u2014 \u65e0\u9700\u518d\u5199 HTTP /
    POST / \u624b\u6413 commandType \u5b57\u7b26\u4e32.
    """

    pass
