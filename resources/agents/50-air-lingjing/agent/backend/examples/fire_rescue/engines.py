"""\u706d\u706b\u4efb\u52a1\u7684 EngineBridge \u5b9e\u73b0.

\u63d0\u4f9b\u4e24\u79cd\u5f15\u64ce\u63a5\u5165:

* :class:`MockFireRescueBridge` \u2014 \u8fdb\u7a0b\u5185\u706b\u707e\u4e16\u754c, \u6a21\u62df UAV FOV \u63a2\u6d4b +
  UGV \u62b5\u8fd1\u706d\u706b + \u591a\u6b65\u706d\u706b\u8fdb\u5ea6.
* :class:`UEFireRescueBridge` \u2014 \u76f4\u63a5\u7ee7\u627f :class:`RealtimeEngineBridge`,
  \u901a\u8fc7 ``realtime_manager.request_to_engine`` \u628a ``resetFireRescueScenario``
  / ``getFireRescueObservation`` / ``dispatchFireRescueAction`` \u63a8\u5230 LJ-ENGINE,
  \u771f\u5b9e WS \u8054\u8c03\u65f6\u76f4\u63a5\u7528.
"""

from __future__ import annotations

import math
from typing import Any

from app.modules.envs.engine_bridge.realtime_bridge import RealtimeEngineBridge
from app.modules.envs.interaction import InteractionConfig
from app.modules.envs.scenario import ScenarioSpec

from examples.fire_rescue.scenario import uav_name, ugv_names


class MockFireRescueBridge:
    """\u8fdb\u7a0b\u5185\u7684\u7b80\u6613\u706b\u707e\u4e16\u754c, \u4e0d\u4f9d\u8d56\u4efb\u4f55\u5916\u90e8 UE \u5de5\u7a0b."""

    def __init__(
        self,
        *,
        fov_radius: float = 60.0,
        extinguish_distance: float = 8.0,
        extinguish_steps_required: int = 3,
    ) -> None:
        self.uav = uav_name()
        self.ugvs = ugv_names()
        self.fov_radius = float(fov_radius)
        self.extinguish_distance = float(extinguish_distance)
        self.extinguish_steps_required = int(extinguish_steps_required)
        self.poses: dict[str, dict[str, float]] = {}
        self.fires: dict[str, dict[str, Any]] = {}
        self._step = 0

    async def reset_scenario(self, spec: ScenarioSpec, cfg: InteractionConfig) -> dict[str, Any]:
        self._step = 0
        self.poses = {}
        for asset in spec.assets:
            pos = asset.position
            self.poses[asset.name] = {
                "x": float(pos.get("x", 0)),
                "y": float(pos.get("y", 0)),
                "z": float(pos.get("z", pos.get("alt", 0))),
            }
        fire_raw: list[dict[str, Any]] = []
        for blueprint in spec.task_matrix:
            spots = blueprint.initial_state.get("fire_spots")
            if spots:
                fire_raw = list(spots)
                break
        self.fires = {}
        for idx, spot in enumerate(fire_raw):
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
        return {
            "status": "reset",
            "uav": self.uav,
            "ugvs": list(self.ugvs),
            "fire_total": len(self.fires),
        }

    def _fov_visible(self, uav_pose: dict[str, float]) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        for fid, fire in self.fires.items():
            if fire["status"] == "extinguished":
                continue
            p = fire["position"]
            d = math.hypot(p["x"] - uav_pose["x"], p["y"] - uav_pose["y"])
            if d <= self.fov_radius:
                out.append(
                    {
                        "id": fid,
                        "position": dict(p),
                        "distance_from_uav": d,
                        "intensity": fire["intensity"],
                        "status": fire["status"],
                    }
                )
        return out

    async def request_observation(
        self, query: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        agents_obs: dict[str, Any] = {}
        uav_pose = self.poses.get(self.uav) or {"x": 0.0, "y": 0.0, "z": 80.0}
        agents_obs[self.uav] = {
            "pose": dict(uav_pose),
            "fov_radius": self.fov_radius,
            "visible_fires": self._fov_visible(uav_pose),
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
                    if f.get("active_extinguisher") == ugv and f["status"] == "in_progress"
                ],
                "extinguished_fires": [
                    fid for fid, f in self.fires.items() if f["status"] == "extinguished"
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
        return {
            "agents": agents_obs,
            "fires": fires_summary,
            "step": self._step,
            "all_extinguished": bool(self.fires)
            and all(f["status"] == "extinguished" for f in self.fires.values()),
        }

    def _parse_offset(self, offset: Any) -> tuple[float, float]:
        if isinstance(offset, (list, tuple)) and len(offset) >= 2:
            return float(offset[0]), float(offset[1])
        if isinstance(offset, dict):
            return float(offset.get("x", 0)), float(offset.get("y", 0))
        return 0.0, 0.0

    async def dispatch_action(
        self, action: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        agents_cmd = action.get("agents") or {}
        applied: dict[str, dict[str, float]] = {}

        uav_cmd = agents_cmd.get(self.uav) or {}
        dx, dy = self._parse_offset(uav_cmd.get("offset"))
        alt_delta = float(uav_cmd.get("altitude_delta", 0.0))
        pose = self.poses.setdefault(self.uav, {"x": 0.0, "y": 0.0, "z": 80.0})
        pose["x"] += dx
        pose["y"] += dy
        pose["z"] = max(20.0, pose["z"] + alt_delta)
        applied[self.uav] = {"dx": dx, "dy": dy, "alt_delta": alt_delta}

        for ugv in self.ugvs:
            cmd = agents_cmd.get(ugv) or {}
            dx, dy = self._parse_offset(cmd.get("offset"))
            pose = self.poses.setdefault(ugv, {"x": 0.0, "y": 0.0, "z": 0.0})
            pose["x"] += dx
            pose["y"] += dy
            applied[ugv] = {"dx": dx, "dy": dy}

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
                    fire["position"]["x"] - pose["x"], fire["position"]["y"] - pose["y"]
                )
                if d <= self.extinguish_distance:
                    fire["status"] = "in_progress"
                    fire["progress"] = int(fire["progress"]) + 1
                    fire["active_extinguisher"] = ugv
                    if fire["progress"] >= self.extinguish_steps_required:
                        fire["status"] = "extinguished"
                        fire["active_extinguisher"] = None

        self._step += 1
        return {
            "status": "ok",
            "applied": applied,
            "fires": {fid: f["status"] for fid, f in self.fires.items()},
        }

    async def call_custom(
        self, command_name: str, payload: dict[str, Any], cfg: InteractionConfig
    ) -> dict[str, Any]:
        return {"status": "noop", "command": command_name}

    async def close(self) -> None:
        return None


class UEFireRescueBridge(RealtimeEngineBridge):
    """\u771f\u5b9e UE \u5f15\u64ce\u6865 \u2014 \u76f4\u63a5\u7ee7\u627f :class:`RealtimeEngineBridge`.

    \u7528\u6237\u62ff\u5230\u672c\u7c7b\u5b9e\u4f8b\u5c31\u80fd\u8ba9 env \u628a\u573a\u666f / \u89c2\u6d4b / \u52a8\u4f5c\u901a\u8fc7
    ``realtime_manager.request_to_engine`` \u63a8\u7ed9 LJ-ENGINE.
    """

    pass
