"""Multimodal LLM policy for the multi-drone delivery task.

The API conforms to the main framework's :class:`app.modules.envs.multiagent.PerAgentPolicy` protocol \u2014
``await policy.act(obs, inbox, scenario, history)`` returns ``(action, outgoing_messages)``.

For the observation / action schema, see ``MultiDroneDeliveryEnv``.
"""

from __future__ import annotations

import json
import logging
import math
from typing import Any

from app.modules.ai.clients import LLMClient, default_llm_client, parse_action_json
from app.modules.envs.multiagent import Message
from app.modules.envs.scenario import ScenarioSpec

logger = logging.getLogger(__name__)

Action = dict[str, Any]
Observation = dict[str, Any]


PROMPT_TEMPLATE = """You are remotely controlling a delivery formation made up of multiple UAVs ({fleet_size} of them).
Based on the observation JSON below, provide the action for this step for every UAV that has not yet delivered.
Return JSON with the schema:
{{
  "drones": {{
    "<drone_name>": {{
      "offset": [dx, dy],     // displacement in the x/y directions this step, in meters, absolute value recommended <= {max_step}
      "speed":  <0~30>,       // recommended speed
      "status": "<approach|hover|deliver|return>"
    }},
    ...
  }}
}}
Do not output any text other than the JSON.
If a UAV already has delivered=true, skip it.
"""


class MultiDroneDeliveryPolicy:
    """Centralized policy: feed Qwen-VL once per step; fall back to a geometric heuristic if no valid JSON is obtained."""

    def __init__(
        self,
        llm: LLMClient | None = None,
        *,
        max_step: float = 25.0,
        cruise_speed: float = 25.0,
    ) -> None:
        self.llm: LLMClient = llm or default_llm_client()
        self.max_step = float(max_step)
        self.cruise_speed = float(cruise_speed)

    async def act(
        self,
        observation: Observation,
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> Action:
        drones_obs = observation.get("drones") or {}
        fleet_size = len(drones_obs)
        prompt = PROMPT_TEMPLATE.format(fleet_size=fleet_size, max_step=self.max_step)

        user_text = (
            f"{prompt}\n"
            f"Task description: {scenario.description or 'multi-drone delivery'}\n"
            f"Observation: {json.dumps(observation, ensure_ascii=False)}\n"
            f"Steps executed so far: {len(history)}\n"
            "Output JSON only."
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": user_text}]
        for name, drone in drones_obs.items():
            if drone.get("camera_rgb"):
                content.append(
                    {
                        "type": "image_url",
                        "image_url": {"url": drone["camera_rgb"], "detail": "low"},
                    }
                )

        try:
            response = await self.llm.chat([{"role": "user", "content": content}])
            parsed = parse_action_json(response)
            if "drones" in parsed and isinstance(parsed["drones"], dict):
                return self._sanitize(parsed, drones_obs)
        except Exception as exc:  # noqa: BLE001
            logger.debug("LLM policy fallback, reason=%s", exc)
        return self._heuristic_action(drones_obs)

    def _sanitize(self, parsed: dict[str, Any], drones_obs: dict[str, Any]) -> Action:
        sanitized: dict[str, dict[str, Any]] = {}
        for name in drones_obs:
            cmd = (parsed.get("drones") or {}).get(name) or {}
            offset = cmd.get("offset")
            if not isinstance(offset, (list, tuple)) or len(offset) < 2:
                offset = self._toward_goal(drones_obs[name])
            dx = max(-self.max_step, min(self.max_step, float(offset[0])))
            dy = max(-self.max_step, min(self.max_step, float(offset[1])))
            sanitized[name] = {
                "offset": [dx, dy],
                "speed": float(cmd.get("speed", self.cruise_speed)),
                "status": str(cmd.get("status", "approach")),
            }
        return {"drones": sanitized}

    def _heuristic_action(self, drones_obs: dict[str, Any]) -> Action:
        drones: dict[str, dict[str, Any]] = {}
        for name, drone in drones_obs.items():
            if drone.get("delivered"):
                drones[name] = {"offset": [0.0, 0.0], "speed": 0.0, "status": "hover"}
                continue
            dx, dy = self._toward_goal(drone)
            drones[name] = {
                "offset": [dx, dy],
                "speed": self.cruise_speed,
                "status": "approach",
            }
        return {"drones": drones}

    def _toward_goal(self, drone: dict[str, Any]) -> tuple[float, float]:
        pose = drone.get("pose") or {}
        goal = drone.get("delivery_target") or {}
        dx = float(goal.get("x", 0)) - float(pose.get("x", 0))
        dy = float(goal.get("y", 0)) - float(pose.get("y", 0))
        norm = math.hypot(dx, dy) or 1.0
        scale = min(self.max_step, norm)
        return dx / norm * scale, dy / norm * scale


def build_delivery_policy(llm: LLMClient | None = None) -> MultiDroneDeliveryPolicy:
    return MultiDroneDeliveryPolicy(llm=llm)


SINGLE_DRONE_PROMPT = """You are controlling a delivery UAV named {name}.
Based on your own observation and the recently received messages from teammates, provide the action that belongs *only to yourself*.
Return JSON of the form:
{{
  "action": {{"offset": [dx, dy], "speed": <0~30>, "status": "<approach|hover|deliver|return>"}},
  "broadcast": [             // optional: messages (broadcasts) you want to send to teammates; may be omitted if not needed
    {{"type": "<event>", "payload": {{...}}}}
  ]
}}
Constraints: for each component of offset, |dx|,|dy| <= {max_step}; do not output any text other than the JSON.
"""


class SingleDronePolicy:
    """Single-drone distributed policy \u2014 one instance per UAV, which looks at *its own observation + inbox* and outputs its own action.

    This class conforms to the :class:`app.modules.envs.multiagent.PerAgentPolicy` protocol,
    and can be plugged directly into the main framework's ``GenericAgent`` as its brain.
    """

    def __init__(
        self,
        name: str,
        llm: LLMClient | None = None,
        *,
        max_step: float = 25.0,
        cruise_speed: float = 25.0,
        approach_broadcast_distance: float = 30.0,
    ) -> None:
        self.name = name
        self.llm = llm or default_llm_client()
        self.max_step = float(max_step)
        self.cruise_speed = float(cruise_speed)
        self.approach_broadcast_distance = float(approach_broadcast_distance)
        self._announced_approach = False
        self._announced_delivered = False

    async def act(
        self,
        observation: dict[str, Any],
        inbox: list[Message],
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> tuple[Action, list[Message]]:
        self_obs = observation.get("self") or {}

        action_from_llm: Action | None = None
        outgoing: list[Message] = []
        try:
            response = await self._consult_llm(observation, inbox, scenario, history)
            parsed = parse_action_json(response)
            raw_action = parsed.get("action") if isinstance(parsed, dict) else None
            if isinstance(raw_action, dict):
                action_from_llm = self._sanitize_action(raw_action, self_obs)
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

        action = action_from_llm or self._heuristic(self_obs)
        outgoing.extend(self._auto_broadcasts(self_obs))
        return action, outgoing

    async def _consult_llm(
        self,
        observation: dict[str, Any],
        inbox: list[Message],
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> str:
        inbox_view = [m.to_dict() if isinstance(m, Message) else m for m in inbox]
        prompt = SINGLE_DRONE_PROMPT.format(name=self.name, max_step=self.max_step)
        text = (
            f"{prompt}\n"
            f"Task: {scenario.description or 'delivery'}\n"
            f"Own observation: {json.dumps(observation, ensure_ascii=False)}\n"
            f"Messages received from teammates: {json.dumps(inbox_view, ensure_ascii=False, default=str)}\n"
            f"History step count: {len(history)}\n"
        )
        content: list[dict[str, Any]] = [{"type": "text", "text": text}]
        if self_camera := (observation.get("self") or {}).get("camera_rgb"):
            content.append({"type": "image_url", "image_url": {"url": self_camera, "detail": "low"}})
        return await self.llm.chat([{"role": "user", "content": content}])

    def _sanitize_action(self, raw: dict[str, Any], self_obs: dict[str, Any]) -> Action:
        offset = raw.get("offset")
        if not isinstance(offset, (list, tuple)) or len(offset) < 2:
            heur = self._heuristic(self_obs)
            offset = heur["offset"]
        dx = max(-self.max_step, min(self.max_step, float(offset[0])))
        dy = max(-self.max_step, min(self.max_step, float(offset[1])))
        return {
            "offset": [dx, dy],
            "speed": float(raw.get("speed", self.cruise_speed)),
            "status": str(raw.get("status", "approach")),
        }

    def _heuristic(self, self_obs: dict[str, Any]) -> Action:
        if self_obs.get("delivered"):
            return {"offset": [0.0, 0.0], "speed": 0.0, "status": "hover"}
        pose = self_obs.get("pose") or {}
        goal = self_obs.get("delivery_target") or {}
        dx = float(goal.get("x", 0)) - float(pose.get("x", 0))
        dy = float(goal.get("y", 0)) - float(pose.get("y", 0))
        norm = math.hypot(dx, dy) or 1.0
        scale = min(self.max_step, norm)
        return {
            "offset": [dx / norm * scale, dy / norm * scale],
            "speed": self.cruise_speed,
            "status": "approach",
        }

    def _auto_broadcasts(self, self_obs: dict[str, Any]) -> list[Message]:
        """Convention: automatically broadcast to teammates at the two milestones of approaching / successful delivery."""

        msgs: list[Message] = []
        distance = float(self_obs.get("distance", 1e9))
        if (
            not self._announced_approach
            and distance <= self.approach_broadcast_distance
            and not self_obs.get("delivered")
        ):
            self._announced_approach = True
            msgs.append(
                Message(
                    sender=self.name,
                    type="approaching_goal",
                    payload={"distance": distance, "drone": self.name},
                )
            )
        if not self._announced_delivered and self_obs.get("delivered"):
            self._announced_delivered = True
            msgs.append(
                Message(
                    sender=self.name,
                    type="delivered",
                    payload={"drone": self.name},
                )
            )
        return msgs


def build_single_drone_policy(name: str, llm: LLMClient | None = None) -> SingleDronePolicy:
    return SingleDronePolicy(name=name, llm=llm)
