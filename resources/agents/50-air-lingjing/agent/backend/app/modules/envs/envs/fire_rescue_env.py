"""``fire_rescue`` Gym \u98ce\u683c\u73af\u5883 \u2014 \u7a7a\u5730\u534f\u540c\u706d\u706b.

\u4efb\u52a1\u8bbe\u5b9a
========

* 1 \u67b6 UAV (``drone1``) \u5728\u9ad8\u7a7a\u5de1\u903b, \u534a\u5f84 ``fov_radius`` \u5185\u53ef\u89c1\u706b\u70b9;
* N \u53f0 UGV (``ugv1`` / ``ugv2`` / ...) \u5728\u5730\u9762\u5f85\u547d, \u63a5 UAV \u8b66\u62a5\u540e\u81ea\u884c\u8c03\u5ea6\u706d\u706b;
* \u706b\u70b9\u7684\u771f\u5b9e\u4f4d\u7f6e\u4ec5 env \u5185\u90e8\u5df2\u77e5, \u667a\u80fd\u4f53\u5fc5\u987b\u901a\u8fc7 UAV \u63a2\u6d4b\u83b7\u5f97.

step \u6d41\u7a0b::

    \u6536\u5230 {"agents": {<name>: action}} \u2500\u2192 bridge \u6d3e\u53d1\u5230 mock world \u6216 \u771f\u5b9e UE
    \u2500\u2500\u2192 \u62c9\u56de\u6700\u65b0\u89c2\u6d4b (\u542b UAV \u89c6\u91ce / UGV \u706d\u706b\u8fdb\u5ea6 / \u5168\u5c40 fires \u72b6\u6001)
    \u2500\u2500\u2192 \u8bc4\u4f30\u5668\u7b97 shaped reward + \u7d2f\u79ef\u6307\u6807

\u516c\u5f00 API:

* :class:`FireRescueEnv` \u2014 \u7ee7\u627f ``BaseEnv``
* :func:`make_env` \u2014 gym ``make`` \u5de5\u5382, \u4e00\u884c\u6784\u9020 episode
* \u590d\u7528 :class:`app.modules.envs.episode_handle.EpisodeHandle`
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


class FireRescueEnv(BaseEnv):
    """\u7a7a\u5730\u534f\u540c\u706d\u706b\u73af\u5883.

    \u52a8\u4f5c schema::

        {
          "agents": {
            "drone1": {"offset": [dx, dy], "altitude_delta": dz, "status": "patrol|track|return"},
            "ugv1":   {"offset": [dx, dy], "action_type": "idle|navigate|extinguish",
                       "target_id": "<fire_id>"|null},
            ...
          }
        }

    \u89c2\u6d4b schema (\u8282\u9009)::

        {
          "agents": {
            "drone1": {"pose": ..., "fov_radius": 60.0, "visible_fires": [...]},
            "ugv1":   {"pose": ..., "extinguish_distance": 8.0,
                       "extinguishing_fires": [...], "extinguished_fires": [...]},
            ...
          },
          "fires": [{"id": "fire-01", "position": {x,y,z}, "status": "active|in_progress|extinguished", "progress": int}],
          "step": int,
          "all_extinguished": bool
        }
    """

    name = "fire_rescue"
    task_type = "fire_rescue"

    @classmethod
    def default_interaction(cls) -> InteractionConfig:
        return InteractionConfig(
            bridge="mock",
            observation=ObservationConfig(
                modalities=["camera_rgb", "pose", "visible_fires", "fires"],
                timeout_sec=5.0,
            ),
            action=ActionConfig(require_ack=False, timeout_sec=2.0),
            engine_commands=EngineCommandConfig(
                request_observation="getFireRescueObservation",
                execute_action="dispatchFireRescueAction",
                reset_scenario="resetScenario",
            ),
        )

    def observation_space_dict(self) -> dict[str, Any]:
        uav_space = DictSpace(
            {
                "pose": Box(-1e6, 1e6, (3,)),
                "fov_radius": Box(0, 1e4, (1,)),
                "visible_fires": TextSpace(2048),
                "camera_rgb": ImageSpace(),
            }
        )
        ugv_space = DictSpace(
            {
                "pose": Box(-1e6, 1e6, (3,)),
                "extinguish_distance": Box(0, 1e4, (1,)),
                "extinguishing_fires": TextSpace(256),
                "extinguished_fires": TextSpace(256),
                "camera_rgb": ImageSpace(),
            }
        )
        return DictSpace(
            {
                "agents": DictSpace({"<uav>": uav_space, "<ugv>": ugv_space}),
                "fires": TextSpace(4096),
                "step": Box(0, 1e5, (1,)),
                "all_extinguished": Box(0, 1, (1,)),
            }
        ).to_dict()

    def action_space_dict(self) -> dict[str, Any]:
        uav_action = DictSpace(
            {
                "offset": Box(-100, 100, (2,)),
                "altitude_delta": Box(-50, 50, (1,)),
                "status": TextSpace(32),
            }
        )
        ugv_action = DictSpace(
            {
                "offset": Box(-100, 100, (2,)),
                "action_type": TextSpace(32),
                "target_id": TextSpace(32),
            }
        )
        return DictSpace(
            {"agents": DictSpace({"<uav>": uav_action, "<ugv>": ugv_action})}
        ).to_dict()


def make_env(
    name: str = "fire_rescue",
    *,
    scenario: ScenarioDefinition | ScenarioSpec | dict[str, Any] | None = None,
    bridge: EngineBridge | None = None,
    evaluator: BaseEvaluator | dict[str, Any] | str | None = None,
    interaction: dict[str, Any] | None = None,
    task_id: str | None = None,
) -> EpisodeHandle:
    """Gym ``make`` \u5de5\u5382."""

    importlib.import_module("app.modules.envs.evaluators.user.fire_rescue_v1")

    if name != "fire_rescue":
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
        spec.task_id = task_id or make_task_id(prefix=spec.task_type or "fire_rescue")

    evaluator_obj: BaseEvaluator | None = None
    eval_spec: dict[str, Any] = {}
    if isinstance(evaluator, str):
        eval_spec = {"name": evaluator}
    elif isinstance(evaluator, dict):
        eval_spec = evaluator
    elif evaluator is None:
        eval_spec = {"name": "fire_rescue_v1"}
    elif callable(getattr(evaluator, "on_step", None)):
        evaluator_obj = evaluator  # type: ignore[assignment]
    else:
        eval_spec = {"name": "fire_rescue_v1"}

    env = FireRescueEnv()
    env.interaction = resolve_interaction(
        env.default_interaction(), spec.to_dict(), interaction or {}
    )
    env.bridge = bridge
    env.evaluator = evaluator_obj or build_evaluator(eval_spec)

    return EpisodeHandle(env, spec)


from app.modules.envs.registry import ENV_DEFINITIONS, EnvDefinition  # noqa: E402

ENV_DEFINITIONS.setdefault(
    "fire_rescue",
    EnvDefinition(
        name="fire_rescue",
        description="\u7a7a\u5730\u534f\u540c\u706d\u706b\u4efb\u52a1: UAV \u5de1\u903b\u53d1\u73b0\u706b\u70b9, UGV \u6536\u8b66\u62a5\u540e\u8c03\u5ea6\u706d\u706b.",
        task_type="fire_rescue",
        factory=FireRescueEnv,
    ),
)
