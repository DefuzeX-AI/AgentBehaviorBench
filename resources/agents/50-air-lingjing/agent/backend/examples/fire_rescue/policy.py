"""Multi-agent policy for the air-ground cooperative firefighting task.

Implements two kinds of single-agent policies, both of which conform to the main framework's
:class:`app.modules.envs.multiagent.PerAgentPolicy` protocol \u2014 they can be fed directly to
``GenericAgent``:

* :class:`UAVSearchPolicy` \u2014 high-altitude patrol; broadcasts ``fire_detected`` when a fire enters the FOV.
* :class:`UGVExtinguishPolicy` \u2014 listens for alerts, preemptively claims a fire (``claim_fire``),
  executes the multi-step ``extinguish`` action after approaching, and broadcasts ``fire_extinguished`` once extinguished.

Each policy first tries to make decisions with an LLM such as Qwen-VL; any exception falls back to a geometric heuristic.
The LLM client defaults to :func:`app.modules.ai.clients.default_llm_client` \u2014
even without an API key configured, the heuristic can still run the demo end to end.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from app.modules.ai.clients import LLMClient, default_llm_client, parse_action_json
from app.modules.envs.multiagent import Message
from app.modules.envs.scenario import ScenarioSpec

from examples.fire_rescue.scenario import patrol_waypoints

logger = logging.getLogger(__name__)

Action = dict[str, Any]
Observation = dict[str, Any]


UAV_PROMPT = """You are controlling a search UAV named {name}; your mission is to patrol above the city looking for fires.
Based on your own observation + the indices of the waypoints already patrolled, provide the action for this step that belongs *only to yourself*.
Return JSON of the form:
{{
  "action": {{
    "offset": [dx, dy],            // displacement in the x/y directions, |dx|,|dy| <= {max_step}
    "altitude_delta": <-10~10>,    // altitude change, usually 0
    "status": "<patrol|track|return>"
  }},
  "broadcast": [                   // optional: messages sent out proactively
    {{"type": "<event>", "payload": {{...}}}}
  ]
}}
Do not output any text other than the JSON.
"""

UGV_PROMPT = """You are controlling an unmanned firefighting ground vehicle named {name}.
Your goal is, after receiving a UAV alert, to autonomously claim an *unclaimed* fire and drive over to extinguish it.
Return JSON of the form:
{{
  "action": {{
    "offset": [dx, dy],            // displacement this step, |dx|,|dy| <= {max_step}
    "action_type": "<idle|navigate|extinguish>",
    "target_id": "<fire_id>|null"  // the fire currently being handled (give null if there is no target)
  }},
  "broadcast": [                   // optional: messages sent out proactively
    {{"type": "<event>", "payload": {{...}}}}
  ]
}}
Do not output any text other than the JSON.
"""


def _hypot(a: dict[str, float], b: dict[str, float]) -> float:
    return math.hypot(float(a.get("x", 0)) - float(b.get("x", 0)),
                      float(a.get("y", 0)) - float(b.get("y", 0)))


class UAVSearchPolicy:
    """UAV patrol + fire-broadcast policy, implementing the ``PerAgentPolicy`` protocol."""

    def __init__(
        self,
        name: str,
        llm: LLMClient | None = None,
        *,
        max_step: float = 20.0,
        arrived_radius: float = 12.0,
        waypoints: list[dict[str, float]] | None = None,
    ) -> None:
        self.name = name
        self.llm = llm or default_llm_client()
        self.max_step = float(max_step)
        self.arrived_radius = float(arrived_radius)
        self.waypoints = waypoints or patrol_waypoints()
        self._wp_idx = 0
        self._detected: set[str] = set()

    async def act(
        self,
        observation: Observation,
        inbox: list[Message],
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> tuple[Action, list[Message]]:
        self_obs = observation.get("self") or {}
        outgoing: list[Message] = []

        # 1. First check whether there is a new fire in the FOV; if so, broadcast it
        visible = self_obs.get("visible_fires") or []
        for fire in visible:
            fid = fire.get("id")
            if fid and fid not in self._detected:
                self._detected.add(fid)
                outgoing.append(
                    Message(
                        sender=self.name,
                        type="fire_detected",
                        payload={
                            "fire_id": fid,
                            "position": dict(fire.get("position") or {}),
                            "intensity": float(fire.get("intensity", 1.0)),
                            "detected_at_step": observation.get("step"),
                        },
                    )
                )

        # 2. Soft-consult the LLM; on failure fall back to the heuristic
        action: Action | None = None
        try:
            text = await self._consult_llm(observation, inbox, scenario, history)
            parsed = parse_action_json(text)
            raw_action = parsed.get("action") if isinstance(parsed, dict) else None
            if isinstance(raw_action, dict):
                action = self._sanitize(raw_action, self_obs)
            for raw_msg in (parsed.get("broadcast") or []) if isinstance(parsed, dict) else []:
                if isinstance(raw_msg, dict) and raw_msg.get("type"):
                    outgoing.append(
                        Message(
                            sender=self.name,
                            type=str(raw_msg["type"]),
                            payload=dict(raw_msg.get("payload") or {}),
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] LLM failed, falling back to heuristic: %s", self.name, exc)

        action = action or self._heuristic_patrol(self_obs)
        return action, outgoing

    async def _consult_llm(
        self,
        observation: dict[str, Any],
        inbox: list[Message],
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> str:
        prompt = UAV_PROMPT.format(name=self.name, max_step=self.max_step)
        inbox_view = [m.to_dict() if isinstance(m, Message) else m for m in inbox]
        text = (
            f"{prompt}\n"
            f"Task: {scenario.description or 'urban fire alert UAV patrol'}\n"
            f"Own observation: {json.dumps(observation, ensure_ascii=False)}\n"
            f"Waypoint sequence: {json.dumps(self.waypoints, ensure_ascii=False)}\n"
            f"Index of the waypoint already reached: {self._wp_idx}\n"
            f"Recent inbox: {json.dumps(inbox_view, ensure_ascii=False, default=str)}\n"
            f"Fires already reported: {sorted(self._detected)}\n"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if cam := (observation.get("self") or {}).get("camera_rgb"):
            content.append({"type": "image_url", "image_url": {"url": cam, "detail": "low"}})
        return await self.llm.chat([{"role": "user", "content": content}])

    def _sanitize(self, raw: dict[str, Any], self_obs: dict[str, Any]) -> Action:
        offset = raw.get("offset")
        if not isinstance(offset, (list, tuple)) or len(offset) < 2:
            heur = self._heuristic_patrol(self_obs)
            offset = heur["offset"]
        dx = max(-self.max_step, min(self.max_step, float(offset[0])))
        dy = max(-self.max_step, min(self.max_step, float(offset[1])))
        return {
            "offset": [dx, dy],
            "altitude_delta": float(raw.get("altitude_delta", 0.0)),
            "status": str(raw.get("status", "patrol")),
        }

    def _heuristic_patrol(self, self_obs: dict[str, Any]) -> Action:
        pose = self_obs.get("pose") or {"x": 0.0, "y": 0.0}
        if not self.waypoints:
            return {"offset": [0.0, 0.0], "altitude_delta": 0.0, "status": "hover"}
        target = self.waypoints[self._wp_idx % len(self.waypoints)]
        dist = _hypot(pose, target)
        if dist <= self.arrived_radius:
            self._wp_idx += 1
            target = self.waypoints[self._wp_idx % len(self.waypoints)]
            dist = _hypot(pose, target)
        norm = dist or 1.0
        scale = min(self.max_step, dist)
        return {
            "offset": [(target["x"] - pose["x"]) / norm * scale, (target["y"] - pose["y"]) / norm * scale],
            "altitude_delta": 0.0,
            "status": "patrol",
        }


class UGVExtinguishPolicy:
    """UGV response + extinguish policy, implementing the ``PerAgentPolicy`` protocol.

    Internally maintains a ``known_fires`` state machine (open / claimed_by_me / claimed_by_other /
    extinguished). In addition to processing messages, it also re-scans inside ``act()`` to ensure the semantics
    stay consistent even in a runtime where the handler and the policy are separated.
    """

    def __init__(
        self,
        name: str,
        llm: LLMClient | None = None,
        *,
        max_step: float = 15.0,
    ) -> None:
        self.name = name
        self.llm = llm or default_llm_client()
        self.max_step = float(max_step)
        self.known_fires: dict[str, dict[str, Any]] = {}
        self.current_target: str | None = None

    def _ingest_message(self, msg: Message) -> None:
        if msg.type == "fire_detected":
            fid = msg.payload.get("fire_id")
            if fid and fid not in self.known_fires:
                self.known_fires[fid] = {
                    "position": dict(msg.payload.get("position") or {}),
                    "status": "open",
                }
        elif msg.type == "claim_fire":
            fid = msg.payload.get("fire_id")
            claimant = msg.payload.get("claimant")
            if fid and fid in self.known_fires and self.known_fires[fid]["status"] == "open":
                self.known_fires[fid]["status"] = (
                    "claimed_by_me" if claimant == self.name else "claimed_by_other"
                )
                self.known_fires[fid]["claimant"] = claimant
        elif msg.type == "fire_extinguished":
            fid = msg.payload.get("fire_id")
            if fid in self.known_fires:
                self.known_fires[fid]["status"] = "extinguished"
                if fid == self.current_target:
                    self.current_target = None

    async def act(
        self,
        observation: Observation,
        inbox: list[Message],
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> tuple[Action, list[Message]]:
        self_obs = observation.get("self") or {}
        outgoing: list[Message] = []

        for msg in inbox:
            self._ingest_message(msg)

        # Extinguish completion reported back by the env
        for fid in self_obs.get("extinguished_fires") or []:
            if fid in self.known_fires and self.known_fires[fid]["status"] != "extinguished":
                self.known_fires[fid]["status"] = "extinguished"
                if fid == self.current_target:
                    outgoing.append(
                        Message(
                            sender=self.name,
                            type="fire_extinguished",
                            payload={"fire_id": fid, "by": self.name},
                        )
                    )
                    self.current_target = None

        # No target -> pick an open fire and claim it
        if self.current_target is None:
            best_fid: str | None = None
            best_dist = float("inf")
            pose = self_obs.get("pose") or {"x": 0.0, "y": 0.0}
            for fid, info in self.known_fires.items():
                if info["status"] != "open":
                    continue
                d = _hypot(pose, info["position"])
                if d < best_dist:
                    best_dist = d
                    best_fid = fid
            if best_fid is not None:
                self.current_target = best_fid
                self.known_fires[best_fid]["status"] = "claimed_by_me"
                outgoing.append(
                    Message(
                        sender=self.name,
                        type="claim_fire",
                        payload={"fire_id": best_fid, "claimant": self.name},
                    )
                )

        # Soft-consult the LLM; use the heuristic on failure
        action: Action | None = None
        try:
            text = await self._consult_llm(observation, inbox, scenario, history)
            parsed = parse_action_json(text)
            raw_action = parsed.get("action") if isinstance(parsed, dict) else None
            if isinstance(raw_action, dict):
                action = self._sanitize(raw_action, self_obs)
            for raw_msg in (parsed.get("broadcast") or []) if isinstance(parsed, dict) else []:
                if isinstance(raw_msg, dict) and raw_msg.get("type"):
                    outgoing.append(
                        Message(
                            sender=self.name,
                            type=str(raw_msg["type"]),
                            payload=dict(raw_msg.get("payload") or {}),
                        )
                    )
        except Exception as exc:  # noqa: BLE001
            logger.debug("[%s] LLM failed, falling back to heuristic: %s", self.name, exc)

        action = action or self._heuristic(self_obs)
        return action, outgoing

    async def _consult_llm(
        self,
        observation: dict[str, Any],
        inbox: list[Message],
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> str:
        prompt = UGV_PROMPT.format(name=self.name, max_step=self.max_step)
        inbox_view = [m.to_dict() if isinstance(m, Message) else m for m in inbox]
        text = (
            f"{prompt}\n"
            f"Task: {scenario.description or 'urban fire alert UGV extinguishing'}\n"
            f"Own observation: {json.dumps(observation, ensure_ascii=False)}\n"
            f"Known fires (this vehicle's view): {json.dumps(self.known_fires, ensure_ascii=False)}\n"
            f"Currently claimed fire: {self.current_target}\n"
            f"Recent inbox: {json.dumps(inbox_view, ensure_ascii=False, default=str)}\n"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if cam := (observation.get("self") or {}).get("camera_rgb"):
            content.append({"type": "image_url", "image_url": {"url": cam, "detail": "low"}})
        return await self.llm.chat([{"role": "user", "content": content}])

    def _sanitize(self, raw: dict[str, Any], self_obs: dict[str, Any]) -> Action:
        offset = raw.get("offset")
        if not isinstance(offset, (list, tuple)) or len(offset) < 2:
            heur = self._heuristic(self_obs)
            offset = heur["offset"]
        dx = max(-self.max_step, min(self.max_step, float(offset[0])))
        dy = max(-self.max_step, min(self.max_step, float(offset[1])))
        action_type = str(raw.get("action_type", "idle"))
        target_id = raw.get("target_id") if raw.get("target_id") not in (None, "null", "") else None
        return {
            "offset": [dx, dy],
            "action_type": action_type,
            "target_id": target_id or self.current_target,
        }

    def _heuristic(self, self_obs: dict[str, Any]) -> Action:
        if self.current_target is None or self.current_target not in self.known_fires:
            return {"offset": [0.0, 0.0], "action_type": "idle", "target_id": None}
        pose = self_obs.get("pose") or {"x": 0.0, "y": 0.0}
        target_pos = self.known_fires[self.current_target]["position"]
        dx = target_pos.get("x", 0) - pose.get("x", 0)
        dy = target_pos.get("y", 0) - pose.get("y", 0)
        distance = math.hypot(dx, dy)
        extinguish_distance = float(self_obs.get("extinguish_distance", 8.0))
        if distance > extinguish_distance:
            norm = distance or 1.0
            scale = min(self.max_step, distance)
            return {
                "offset": [dx / norm * scale, dy / norm * scale],
                "action_type": "navigate",
                "target_id": self.current_target,
            }
        return {
            "offset": [0.0, 0.0],
            "action_type": "extinguish",
            "target_id": self.current_target,
        }


def build_uav_search_policy(name: str, llm: LLMClient | None = None) -> UAVSearchPolicy:
    return UAVSearchPolicy(name=name, llm=llm)


def build_ugv_extinguish_policy(name: str, llm: LLMClient | None = None) -> UGVExtinguishPolicy:
    return UGVExtinguishPolicy(name=name, llm=llm)
