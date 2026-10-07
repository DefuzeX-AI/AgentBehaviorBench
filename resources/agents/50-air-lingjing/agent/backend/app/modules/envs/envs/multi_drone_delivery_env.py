"""``multi_drone_delivery`` Gym \u98ce\u683c\u73af\u5883 (\u9879\u76ee\u4e3b\u6846\u67b6\u7248).

\u516c\u5f00 API:

* :class:`MultiDroneDeliveryEnv` \u2014 \u7ee7\u627f ``BaseEnv``, \u63d0\u4f9b reset/step/close.
* :func:`make_env` \u2014 \u4e00\u884c\u6784\u9020 + \u81ea\u52a8\u7ed1\u5b9a scenario / bridge / evaluator,
  \u4e0e OpenAI gym \u7684 ``gym.make`` \u7528\u6cd5\u5bf9\u9f50.
* :class:`EpisodeHandle` \u2014 gym-style \u5305\u88c5, \u628a env \u4e0e\u672c episode \u7684 ScenarioSpec
  \u7ed1\u5728\u4e00\u8d77, \u66b4\u9732 ``reset / step / close`` \u4e09\u4ef6\u5957.

\u8ddf\u5177\u4f53 case (\u793a\u4f8b) \u89e3\u8026\u540e, \u4efb\u4f55 ``examples/<case>/`` \u90fd\u53ef\u4ee5
``from app.modules.envs.envs.multi_drone_delivery_env import make_env`` \u76f4\u63a5\u590d\u7528.
"""

from __future__ import annotations

import importlib
from typing import Any

from app.modules.envs.base import BaseEnv
from app.modules.envs.engine_bridge.base import EngineBridge
from app.modules.envs.episode_handle import EpisodeHandle
from app.modules.envs.evaluators import build_evaluator
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
from app.modules.envs.spaces import Box, DictSpace, ImageSpace, TextSpace
from app.modules.envs.task_id import make_task_id


class MultiDroneDeliveryEnv(BaseEnv):
    """\u591a\u65e0\u4eba\u673a\u914d\u9001\u73af\u5883.

    \u6bcf\u4e00 step:
      1. \u6536\u5230\u4e00\u4e2a ``{"drones": {<name>: {offset/speed/status}}}`` \u52a8\u4f5c.
      2. \u901a\u8fc7 bridge \u6d3e\u53d1 (Mock \u76f4\u63a5\u66f4\u65b0\u4e16\u754c / Realtime \u8d70 WS \u63a8\u5230 UE).
      3. bridge \u62c9\u56de\u6700\u65b0 ``drones`` \u89c2\u6d4b.
      4. \u8bc4\u4f30\u5668\u7b97 shaped reward + \u7d2f\u79ef\u6307\u6807.
    """

    name = "multi_drone_delivery"
    task_type = "multi_drone_delivery"

    @classmethod
    def default_interaction(cls) -> InteractionConfig:
        return InteractionConfig(
            bridge="mock",
            observation=ObservationConfig(
                modalities=["camera_rgb", "pose", "delivery_target"],
                timeout_sec=5.0,
            ),
            action=ActionConfig(require_ack=False, timeout_sec=2.0),
            engine_commands=EngineCommandConfig(
                request_observation="getFleetObservation",
                execute_action="dispatchFleetAction",
                reset_scenario="resetScenario",
            ),
        )

    def observation_space_dict(self) -> dict[str, Any]:
        per_drone = DictSpace(
            {
                "pose": Box(-1e6, 1e6, (3,)),
                "delivery_target": Box(-1e6, 1e6, (3,)),
                "distance": Box(0, 1e9, (1,)),
                "delivered": Box(0, 1, (1,)),
                "camera_rgb": ImageSpace(),
            }
        )
        return DictSpace(
            {"drones": per_drone, "step": Box(0, 1e5, (1,)), "all_delivered": Box(0, 1, (1,))}
        ).to_dict()

    def action_space_dict(self) -> dict[str, Any]:
        per_drone = DictSpace(
            {
                "offset": Box(-100, 100, (2,)),
                "speed": Box(0, 60, (1,)),
                "status": TextSpace(32),
            }
        )
        return DictSpace({"drones": per_drone}).to_dict()


def make_env(
    name: str = "multi_drone_delivery",
    *,
    scenario: ScenarioDefinition | ScenarioSpec | dict[str, Any] | None = None,
    bridge: EngineBridge | None = None,
    evaluator: BaseEvaluator | dict[str, Any] | str | None = None,
    interaction: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> EpisodeHandle:
    """Gym ``make`` \u98ce\u683c\u5de5\u5382.

    \u8fd4\u56de :class:`EpisodeHandle`; \u76f4\u63a5 ``await handle.reset()``, \u7136\u540e\u5faa\u73af
    ``await handle.step(action)`` \u5373\u53ef, \u5b8c\u5168 in-process.
    """

    
    importlib.import_module("app.modules.envs.evaluators.user.delivery_v1")

    if name != "multi_drone_delivery":
        raise ValueError(f"\u672a\u77e5\u7684\u73af\u5883\u540d: {name}")

    if isinstance(scenario, ScenarioDefinition):
        spec = ScenarioSpec.from_definition(scenario)
    elif isinstance(scenario, ScenarioSpec):
        spec = scenario
    elif isinstance(scenario, dict):
        spec = ScenarioSpec.from_obj(scenario)
    else:
        raise ValueError("scenario \u4e0d\u80fd\u4e3a\u7a7a, \u8bf7\u4f20 ScenarioDefinition / ScenarioSpec / dict")

    if not spec.task_id:
        spec.task_id = task_id or make_task_id(prefix=spec.task_type or "task")

    evaluator_obj: BaseEvaluator | None = None
    eval_spec: dict[str, Any] = {}
    if isinstance(evaluator, str):
        eval_spec = {"name": evaluator}
    elif isinstance(evaluator, dict):
        eval_spec = evaluator
    elif evaluator is None:
        eval_spec = {"name": "delivery_v1"}
    elif callable(getattr(evaluator, "on_step", None)):
        evaluator_obj = evaluator  # type: ignore[assignment]
    else:
        eval_spec = {"name": "delivery_v1"}

    env = MultiDroneDeliveryEnv()
    env.interaction = resolve_interaction(
        env.default_interaction(), spec.to_dict(), interaction or {}
    )
    env.bridge = bridge
    env.evaluator = evaluator_obj or build_evaluator(eval_spec)

    return EpisodeHandle(env, spec)


from app.modules.envs.registry import ENV_DEFINITIONS, EnvDefinition  # noqa: E402

ENV_DEFINITIONS.setdefault(
    "multi_drone_delivery",
    EnvDefinition(
        name="multi_drone_delivery",
        description="\u591a\u65e0\u4eba\u673a\u914d\u9001\u4efb\u52a1: \u5404\u673a\u62b5\u8fd1\u5404\u81ea\u914d\u9001\u70b9 + \u81ea\u52a8\u8bc4\u4f30.",
        task_type="multi_drone_delivery",
        factory=MultiDroneDeliveryEnv,
    ),
)
