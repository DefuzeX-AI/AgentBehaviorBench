"""Environment definition for the single-drone fire case."""

from __future__ import annotations

from typing import Any

from app.modules.envs.base import BaseEnv
from app.modules.envs.engine_bridge.base import EngineBridge
from app.modules.envs.episode_handle import EpisodeHandle
from app.modules.envs.evaluators.base import BaseEvaluator
from app.modules.envs.interaction import (
    ActionConfig,
    EngineCommandConfig,
    InteractionConfig,
    ObservationConfig,
    resolve_interaction,
)
from app.modules.envs.scenario import ScenarioSpec
from app.modules.envs.scenario_models import ScenarioDefinition
from app.modules.envs.spaces import Box, DictSpace, Discrete, ImageSpace, TextSpace
from app.modules.envs.task_id import make_task_id

from examples.singledrone_fire.evaluator import SingleDroneFireEvaluator


class SingleDroneFireEnv(BaseEnv):
    name = "singledrone_fire"
    task_type = "singledrone_fire"

    def _persist(self, payload: dict[str, Any]) -> None:
        """Keep this example self-contained; do not write global sim_data rows."""

        return None

    @classmethod
    def default_interaction(cls) -> InteractionConfig:
        return InteractionConfig(
            bridge="mock",
            observation=ObservationConfig(
                modalities=["global_rgb", "topdown_rgb", "pose"],
                timeout_sec=5.0,
            ),
            action=ActionConfig(require_ack=False, timeout_sec=2.0),
            engine_commands=EngineCommandConfig(
                request_observation="getSingleDroneFireObservation",
                execute_action="dispatchSingleDroneFireAction",
                reset_scenario="resetScenario",
            ),
        )

    def observation_space_dict(self) -> dict[str, Any]:
        topdown_meta = DictSpace(
            {
                "center_x": Box(-1e6, 1e6, (1,)),
                "center_y": Box(-1e6, 1e6, (1,)),
                "side_length_m": Box(0, 1e6, (1,)),
                "length_m": Box(0, 1e6, (1,)),
                "width_m": Box(0, 1e6, (1,)),
                "meter_per_pixel_x": Box(0, 1e6, (1,)),
                "meter_per_pixel_y": Box(0, 1e6, (1,)),
                "image_width": Box(1, 1e5, (1,)),
                "image_height": Box(1, 1e5, (1,)),
            }
        )
        per_agent = DictSpace(
            {
                "pose": Box(-1e6, 1e6, (3,)),
                "global_rgb": ImageSpace(),
                "topdown_rgb": ImageSpace(),
                "topdown_meta": topdown_meta,
            }
        )
        return DictSpace(
            {
                "agents": DictSpace({"drone1": per_agent}),
                "step": Box(0, 1e5, (1,)),
            }
        ).to_dict()

    def action_space_dict(self) -> dict[str, Any]:
        per_agent = DictSpace(
            {
                "offset": Box(-1e6, 1e6, (2,)),
                "altitude_delta": Box(-50, 50, (1,)),
                "status": TextSpace(32),
                "thought_process": TextSpace(8192),
                "predicted_target_coord": Box(-1e6, 1e6, (2,)),
                "current_coord": Box(-1e6, 1e6, (2,)),
                "fire_detected": Discrete(2),
                "fire_estimate_world": DictSpace(
                    {
                        "x": Box(-1e6, 1e6, (1,)),
                        "y": Box(-1e6, 1e6, (1,)),
                        "z": Box(-1e6, 1e6, (1,)),
                    }
                ),
                "annotation_image": ImageSpace(),
                "vlm_metadata": DictSpace({}),
            }
        )
        return DictSpace({"agents": DictSpace({"drone1": per_agent})}).to_dict()


def make_env(
    *,
    scenario: ScenarioDefinition | ScenarioSpec | dict[str, Any],
    bridge: EngineBridge | None = None,
    evaluator: BaseEvaluator | None = None,
    interaction: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> EpisodeHandle:
    if isinstance(scenario, ScenarioDefinition):
        spec = ScenarioSpec.from_definition(scenario)
    elif isinstance(scenario, ScenarioSpec):
        spec = scenario
    elif isinstance(scenario, dict):
        spec = ScenarioSpec.from_obj(scenario)
    else:
        raise ValueError("scenario \u4e0d\u80fd\u4e3a\u7a7a")

    if not spec.task_id:
        spec.task_id = task_id or make_task_id(prefix=spec.task_type or "singledrone_fire")

    env = SingleDroneFireEnv()
    env.interaction = resolve_interaction(
        env.default_interaction(), spec.to_dict(), interaction or {}
    )
    env.bridge = bridge
    env.evaluator = evaluator or SingleDroneFireEvaluator()
    return EpisodeHandle(env, spec)
