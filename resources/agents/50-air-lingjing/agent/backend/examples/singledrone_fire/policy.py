"""Policy for the single-drone fire reconnaissance case."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.modules.ai.clients import LLMClient, default_llm_client, parse_action_json
from app.modules.envs.scenario import ScenarioSpec

Action = dict[str, Any]
Observation = dict[str, Any]

CASE_DIR = Path(__file__).resolve().parent
PROMPT_PATH = CASE_DIR / "prompts" / "navigation_policy.txt"
LEGACY_PROMPT_PATH = CASE_DIR / "prompt.txt"

DEFAULT_PROMPT = """<Role>
You are an autonomous navigation UAV specialized in spatial reasoning, target localization, and fire reconnaissance.
</Role>

<Target_Description>
You are searching for a specific playground/sports field (the primary target).
Because the playground is small and hard to distinguish on the global map, you must locate it using the following anchor landmark:

- Anchor landmark: a bright white circular stadium with a large dome, located in the northwest quadrant (upper-left region), surrounded by an open plaza.
- Primary target (the playground): located to the northwest of the anchor landmark and immediately adjacent to it.

In the 400m x 300m top-down local view, the primary target will appear as red running-track lines, green lawn, or open-field texture, rather than a white dome.
</Target_Description>

<Inputs_and_Map_Properties>
You will receive two images strictly in the following order:
1. Image 1 (global map): 385x385 pixels, corresponding to 6000m x 6000m of actual ground. Use it only in Step 3 to compute global relocalization.
   - Origin: the lower-left corner is [0, 0] and the upper-right corner is [385, 385].
   - Scale: 1 global-image pixel = 6000 / 385 = 15.5844 meters.
   - Visual cue: your current position is the center of the solid green dot. The past flight path is a red line.
2. Image 2 (top-down camera image): the local view directly below the UAV. Resolution is 400x300 pixels, corresponding to 400m x 300m of actual ground.
   - Scale: 1 top-down-view pixel = 1 meter.
   - The image center corresponds to the UAV's current position.
   - x to the right is east, y upward is north; if reading from image coordinates, a downward-on-screen pixel difference must be converted to a negative dy.
   - This image is used in Step 1 to confirm whether the target area has been reached and to detect fire.
</Inputs_and_Map_Properties>

<Coordinate_System>
For the final output [dx, dy] offset:
- offset must be output in units of actual ground meters, because the flight controller executes distances in meters.
- dx (horizontal): to the right (east) is positive (+), to the left (west) is negative (-).
- dy (vertical): upward (north) is positive (+), downward (south) is negative (-).
- If computing from the global map:
  global_dx_px = target_x - current_x
  global_dy_px = target_y - current_y
  dx_m = global_dx_px * 15.5844
  dy_m = global_dy_px * 15.5844
- If doing a local search from the top-down view:
  local_dx_m = local_dx_px
  local_dy_m = local_dy_px
</Coordinate_System>

<Execution_Steps>
Step 1: Local verification and reconnaissance
Inspect Image 2 (top-down camera image).
Are the visual features of the primary target (playground/sports-field texture) clearly visible?
If so, scan the visible area and determine whether there is open flame, a smoke plume, or structural damage.

Step 2: Status determination
- If fire is detected (regardless of whether the target is visible): trigger the emergency coverage logic. The task is complete. Set status to "stop", set fire_detected to true, and set offset to [0, 0], indicating hover and report.
- If the target is visible but there is no fire: set status to "continue" and fire_detected to false. Skip Step 3. Output a small local [dx, dy] offset, for example 10 to 20 meters, to perform an expanding square or spiral search pattern around the playground in order to continue looking for fire.
- If the target is not visible and there is no fire: set status to "continue" and fire_detected to false. Proceed to Step 3 and navigate globally using the anchor landmark.

Step 3: Global relocalization and navigation (only performed when the target is not seen)
Target coordinate computation:
  a. Scan Image 1 (global map) and find the anchor landmark (the bright white domed stadium).
  b. Based on that landmark's position, infer the precise absolute pixel coordinates of the primary target (the playground) -> [target_x, target_y].
Current coordinate: find the center of the solid green dot in Image 1 -> [current_x, current_y].
Offset computation: first compute the global-image pixel difference, then convert to ground meters.
  global_dx_px = target_x - current_x
  global_dy_px = target_y - current_y
  dx = global_dx_px * 15.5844
  dy = global_dy_px * 15.5844
</Execution_Steps>

<Output_Format>
Return only a valid JSON object. Do not include markdown code fences, for example ```json. Use the following structure and replace the example coordinates with actual numbers:

{
  "thought_process": "1. Analyze the top-down image... 2. Determine whether the target/fire is visible... 3. Perform the math from global pixel difference to ground meters, or from local top-down pixels to ground meters...",
  "status": "continue",
  "predicted_target_coord": [250, 320],
  "current_coord": [180, 300],
  "offset": [1090.91, 311.69],
  "fire_detected": false
}
</Output_Format>
"""


def load_prompt() -> str:
    for path in (PROMPT_PATH, LEGACY_PROMPT_PATH):
        try:
            text = path.read_text(encoding="utf-8").strip()
        except OSError:
            continue
        if text:
            return text
    return DEFAULT_PROMPT


class SingleDroneFirePolicy:
    """LLM policy that turns two visual observations into a drone action."""

    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        max_step: float = 30.0,
    ) -> None:
        self.llm = llm or default_llm_client()
        self.max_step = float(max_step)
        self.prompt_template = load_prompt()

    async def act(
        self,
        observation: Observation,
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> Action:
        response = await self._consult_llm(observation, scenario, history)
        parsed = parse_action_json(response)
        if not isinstance(parsed, dict):
            raise ValueError(f"LLM output must be a JSON object: {response}")
        if isinstance(parsed.get("action"), dict):
            raise ValueError(f"LLM output still uses the old action protocol; please use the new workflow schema: {response}")

        action = self._sanitize_action(parsed)
        return {"agents": {"drone1": action}}

    async def _consult_llm(
        self,
        observation: Observation,
        scenario: ScenarioSpec,
        history: list[dict[str, Any]],
    ) -> str:
        prompt = self.prompt_template
        payload = {
            "task": scenario.description,
            "coordinate_contract": {
                "output_offset_unit": "meter",
                "global_image_px": [385, 385],
                "global_ground_m": [6000.0, 6000.0],
                "global_meter_per_pixel": 6000.0 / 385.0,
                "topdown_image_px": [400, 300],
                "topdown_ground_m": [400.0, 300.0],
                "topdown_meter_per_pixel": [1.0, 1.0],
            },
            "observation": self._context_without_images(observation),
            "history_steps": len(history),
        }
        content: list[dict[str, Any]] = [
            {
                "type": "text",
                "text": f"{prompt}\nContext JSON: {json.dumps(payload, ensure_ascii=False)}",
            }
        ]
        agent_obs = (observation.get("agents") or {}).get("drone1") or {}
        if agent_obs.get("global_rgb"):
            content.append({"type": "text", "text": "Image 1 (global map) follows."})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": agent_obs["global_rgb"], "detail": "low"},
                }
            )
        if agent_obs.get("topdown_rgb"):
            content.append({"type": "text", "text": "Image 2 (top-down camera image) follows."})
            content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": agent_obs["topdown_rgb"], "detail": "low"},
                }
            )
        return await self.llm.chat([{"role": "user", "content": content}])

    def _sanitize_action(self, raw: dict[str, Any]) -> dict[str, Any]:
        required = {
            "thought_process",
            "status",
            "predicted_target_coord",
            "current_coord",
            "offset",
            "fire_detected",
        }
        missing = sorted(required - set(raw))
        if missing:
            raise ValueError(f"LLM output is missing fields {missing}: {raw}")

        status = str(raw["status"])
        if status not in {"continue", "stop"}:
            raise ValueError(f"unknown status={status}, allowed=['continue', 'stop']")

        fire_detected = raw["fire_detected"]
        if not isinstance(fire_detected, bool):
            raise ValueError(f"fire_detected must be a JSON boolean: {raw}")

        offset = raw.get("offset")
        if not isinstance(offset, (list, tuple)) or len(offset) < 2:
            raise ValueError(f"offset must be an array of length 2: {raw}")
        dx = float(offset[0])
        dy = float(offset[1])

        predicted = self._coord_pair(raw["predicted_target_coord"], "predicted_target_coord")
        current = self._coord_pair(raw["current_coord"], "current_coord")

        if fire_detected or status == "stop":
            status = "stop"
            dx = 0.0
            dy = 0.0

        return {
            "offset": [dx, dy],
            "altitude_delta": 0.0,
            "status": status,
            "thought_process": str(raw["thought_process"]),
            "predicted_target_coord": predicted,
            "current_coord": current,
            "fire_detected": fire_detected,
        }

    @staticmethod
    def _coord_pair(value: Any, field_name: str) -> list[float]:
        if not isinstance(value, (list, tuple)) or len(value) < 2:
            raise ValueError(f"{field_name} must be an array of length 2: {value}")
        return [float(value[0]), float(value[1])]

    @staticmethod
    def _context_without_images(observation: Observation) -> Observation:
        copied = json.loads(json.dumps(observation, ensure_ascii=False, default=str))
        agent_obs = (copied.get("agents") or {}).get("drone1") or {}
        for key in ("global_rgb", "topdown_rgb"):
            if agent_obs.get(key):
                agent_obs[key] = f"<{key} attached as image_url>"
        return copied


def build_single_drone_fire_policy(
    *,
    llm: LLMClient | None = None,
    annotator: Any | None = None,
) -> SingleDroneFirePolicy:
    _ = annotator
    return SingleDroneFirePolicy(llm=llm)
