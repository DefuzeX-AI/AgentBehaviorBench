"""\u591a\u667a\u80fd\u4f53\u95ed\u73af runtime \u2014 \u628a env + agents + MessageBus \u4e32\u8d77\u6765.

\u8c03\u5ea6\u65f6\u5e8f::

    \u6bcf\u4e2a env step \u5185\u4e09\u9636\u6bb5:
      phase 1: \u6bcf\u4e2a agent process_inbox() \u5904\u7406\u4e0a\u8f6e\u6536\u5230\u7684\u6d88\u606f
      phase 2: \u6bcf\u4e2a agent act(self_obs, scenario, inbox) \u2192 (action, outgoing)
      phase 3: env.step({action_key: {name: action}}) \u63a8\u8fdb\u4e16\u754c

\u8bbe\u8ba1\u8981\u70b9
--------

* runtime \u53ea\u4f9d\u8d56 :class:`BaseAgent` \u62bd\u8c61 + \u4e00\u4e2a env handle (gym-like reset/step/close).
  \u5177\u4f53 case \u600e\u4e48\u5b9e\u73b0 env / policy / bridge \u90fd\u884c.
* ``action_key`` \u51b3\u5b9a env.step \u7684\u9876\u5c42 key; \u591a\u673a\u914d\u9001\u7528 ``"drones"``,
  \u706d\u706b case \u7528 ``"agents"`` \u6216 ``"fleet"``, \u9ed8\u8ba4 ``"agents"``.
* runtime \u8fd8\u4f1a\u81ea\u52a8\u55c5\u63a2 ``drones``/``fleet`` \u7b49\u5386\u53f2\u547d\u540d, \u517c\u5bb9\u8001 env.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable

from app.modules.envs.multiagent.agent import BaseAgent
from app.modules.envs.multiagent.messaging import MessageBus

logger = logging.getLogger(__name__)


@runtime_checkable
class EpisodeHandleProtocol(Protocol):
    """runtime \u671f\u671b\u7684 env handle \u534f\u8bae."""

    task_id: str
    scenario: Any
    max_steps: int
    cumulative_reward: float
    metrics: dict[str, float]

    async def reset(self) -> tuple[dict[str, Any], dict[str, Any]]: ...

    async def step(
        self, action: dict[str, Any]
    ) -> tuple[dict[str, Any], float, bool, bool, dict[str, Any]]: ...

    async def close(self) -> None: ...


@dataclass
class StepRecord:
    step: int
    actions: dict[str, dict[str, Any]] = field(default_factory=dict)
    reward: float = 0.0
    inbox_sizes: dict[str, int] = field(default_factory=dict)
    per_agent_obs: dict[str, dict[str, Any]] = field(default_factory=dict)
    terminated: bool = False
    truncated: bool = False


@dataclass
class RunResult:
    task_id: str
    steps: list[StepRecord]
    cumulative_reward: float
    metrics: dict[str, float]
    per_agent: dict[str, dict[str, Any]]
    messages: list[dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "steps": [s.__dict__ for s in self.steps],
            "cumulative_reward": self.cumulative_reward,
            "metrics": self.metrics,
            "per_agent": self.per_agent,
            "messages": self.messages,
        }


PerAgentSliceFn = Callable[[str, dict[str, Any], "MultiAgentRuntime"], dict[str, Any]]


class MultiAgentRuntime:
    """env / agents / message-bus \u7684\u7f16\u6392\u5668, \u4e0d\u7ed1\u5b9a\u5177\u4f53 case."""

    def __init__(
        self,
        env: EpisodeHandleProtocol,
        agents: list[BaseAgent],
        bus: MessageBus,
        *,
        action_key: str = "agents",
        per_agent_obs: PerAgentSliceFn | None = None,
    ) -> None:
        self.env = env
        self.agents: dict[str, BaseAgent] = {a.name: a for a in agents}
        self.bus = bus
        self.action_key = action_key
        self._per_agent_obs = per_agent_obs

    def _slice_obs(self, name: str, global_obs: dict[str, Any]) -> dict[str, Any]:
        if self._per_agent_obs is not None:
            return self._per_agent_obs(name, global_obs, self)
        agents_obs = (
            global_obs.get(self.action_key)
            or global_obs.get("agents")
            or global_obs.get("drones")
            or global_obs.get("fleet")
            or {}
        )
        self_obs = agents_obs.get(name) or {}
        fleet_status = {
            other: bool(
                (agents_obs.get(other) or {}).get("delivered")
                or (agents_obs.get(other) or {}).get("done")
            )
            for other in self.agents
            if other != name
        }
        return {
            "self": self_obs,
            "step": global_obs.get("step"),
            "fleet_status": fleet_status,
            "global": {
                k: v
                for k, v in global_obs.items()
                if k not in {self.action_key, "agents", "drones", "fleet"}
            },
            "subscribers": self.bus.subscribers(),
        }

    async def run(self, max_steps: int | None = None, *, verbose: bool = False) -> RunResult:
        for agent in self.agents.values():
            agent.reset()
        obs, _info = await self.env.reset()
        if verbose:
            print(f"[runtime] reset done, agents={list(self.agents)} task_id={self.env.task_id}")

        steps_limit = max_steps or getattr(self.env, "max_steps", 60)
        steps: list[StepRecord] = []

        for step_idx in range(1, steps_limit + 1):
            inbox_sizes: dict[str, int] = {}
            for name, agent in self.agents.items():
                delivered = await agent.process_inbox()
                inbox_sizes[name] = len(delivered)

            actions: dict[str, dict[str, Any]] = {}
            per_agent_obs: dict[str, dict[str, Any]] = {}
            for name, agent in self.agents.items():
                view = self._slice_obs(name, obs)
                per_agent_obs[name] = view
                last_inbox = (
                    agent.incoming_log[-inbox_sizes[name]:] if inbox_sizes[name] else []
                )
                action, outgoing = await agent.act(view, self.env.scenario, last_inbox)
                actions[name] = action
                if verbose and outgoing:
                    for m in outgoing:
                        print(f"  [msg] {m}")

            combined = {self.action_key: actions}
            obs, reward, terminated, truncated, info = await self.env.step(combined)
            steps.append(
                StepRecord(
                    step=step_idx,
                    actions=actions,
                    reward=float(reward),
                    inbox_sizes=inbox_sizes,
                    per_agent_obs=per_agent_obs,
                    terminated=bool(terminated),
                    truncated=bool(truncated),
                )
            )
            if verbose:
                inbox_digest = ", ".join(f"{k}:{v}" for k, v in inbox_sizes.items() if v)
                tag = f"  inbox=[{inbox_digest}]" if inbox_digest else ""
                print(f"  step {step_idx:>2}: reward={reward:+.3f}{tag}")
            if terminated or truncated:
                break

        per_agent = {
            name: {
                "stats": agent.stats(),
                "sent_log": [m.to_dict() for m in agent.outgoing_log],
                "received_log": [m.to_dict() for m in agent.incoming_log],
            }
            for name, agent in self.agents.items()
        }
        return RunResult(
            task_id=self.env.task_id,
            steps=steps,
            cumulative_reward=self.env.cumulative_reward,
            metrics=self.env.metrics,
            per_agent=per_agent,
            messages=[m.to_dict() for m in self.bus.history()],
        )
