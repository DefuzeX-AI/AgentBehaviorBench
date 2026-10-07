"""ABB message/result boundary for seanlxh/Air-Lingjing.

Upstream entrypoint: the project's registered LangGraph workflow
``open_vocab_navigation_env_loop`` (``backend/app/modules/agents/loop.py``). It is
reached the same way the FastAPI service reaches it — ``app.modules.agents.registry``
imports every task module, and ``invoke_agent`` compiles ``AGENT_DEFINITION.builder()``
and awaits the compiled graph. This binding uses that registry rather than importing
the module directly, so the unit exercises the project's real agent surface.

That graph is the project's closed-loop embodied agent: it creates one Gym-style
episode through ``app.modules.envs`` and then, on every step, asks the configured
multimodal LLM for a single JSON action and applies it to the environment. The
environment's interaction bridge defaults to the in-process mock engine
(``app/modules/envs/engine_bridge/mock_bridge.py``), so an evaluation needs neither
Unreal Engine nor the SQLite persistence layer.

If the model call fails or returns something unparsable, the upstream policy falls
back to a heuristic action instead of raising, so a Case still produces a trajectory.

ABB contract: one Case Input is the mission goal of the episode; the answer is a
plain-text summary of the perceive-think-act loop that ran.
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path

# ABB imports this binding from bindings/, so the upstream package root (backend/,
# which holds the top-level `app` package) is not on sys.path yet.
_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent" / "backend"
if str(_SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(_SOURCE_ROOT))

AGENT_NAME = "open_vocab_navigation_env_loop"
ENVIRONMENT_NAME = "open_vocab_navigation"
SCENARIO_PATH = _SOURCE_ROOT / "app" / "modules" / "envs" / "scenarios" / "open_vocab_navigation.json"

# One Case is one episode. The bundled scenario allows 30 steps; each step is a model
# call, so a Case is bounded here and the bound is stated in requirement.md.
DEFAULT_MAX_STEPS = 6


def _trust_run_certificate() -> None:
    """Point certifi at the trust bundle the run already prepared.

    The upstream analysis service builds ``httpx.AsyncClient(..., trust_env=False)``, and
    httpx honours ``SSL_CERT_FILE`` only when ``trust_env`` is true (``httpx/_config.py``);
    otherwise it verifies against ``certifi.where()``. The ABB worker has already written
    the merged bundle (public roots plus the interceptor certificate) and pointed
    ``SSL_CERT_FILE`` at it, so make certifi resolve to that same file rather than writing
    a bundle of our own. Requests, routing and credentials are untouched.
    """

    bundle = os.environ.get("SSL_CERT_FILE")
    if not bundle or not os.path.isfile(bundle):
        print(
            f"[abb-binding] no trust bundle at SSL_CERT_FILE={bundle!r}; "
            "httpx will use the bundled public roots",
            flush=True,
        )
        return
    try:
        import certifi

        certifi.where = lambda: bundle
        print(f"[abb-binding] certifi now verifies against {bundle}", flush=True)
    except Exception as exc:  # noqa: BLE001 - report instead of silently losing trust
        print(
            f"[abb-binding] could not redirect certifi to {bundle}: {type(exc).__name__}: {exc}",
            flush=True,
        )


def _scenario(mission: str) -> dict:
    """Load the project's own scenario and make the Case Input its mission goal."""

    payload = json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))
    payload["description"] = mission
    return payload


def _mission(value: object) -> str:
    if isinstance(value, Mapping):
        for key in ("message", "input", "mission", "goal"):
            candidate = value.get(key)
            if isinstance(candidate, str) and candidate.strip():
                return candidate.strip()
        raise ValueError("Supply the Case Input as message text")
    if isinstance(value, str) and value.strip():
        return value.strip()
    raise ValueError("Supply the Case Input as message text")


def _summarise(mission: str, scenario: dict, state: Mapping) -> str:
    """Render the episode outcome as a compact plain-text Case answer.

    The per-step trajectory stays in the raw output and the run's evidence; this is the
    answer text, so it reports what the episode did rather than dumping every record.
    """

    trajectory = list(state.get("trajectory") or [])
    metrics = state.get("metrics") or {}
    targets = scenario.get("targets") or []
    lines = [
        f"Mission: {mission}",
        f"Environment: {ENVIRONMENT_NAME} (in-process mock engine, no Unreal Engine)",
        f"Goal target: {targets[0].get('description') if targets else 'n/a'}",
        f"Episode: {state.get('episode_id')}",
        f"Steps executed: {len(trajectory)}",
        f"Cumulative reward: {state.get('cumulative_reward')}",
    ]
    if metrics:
        lines.append("Final metrics: " + json.dumps(metrics, ensure_ascii=False, sort_keys=True))
    actions = [
        f"{step.get('action', {}).get('offset')}@{step.get('action', {}).get('speed')}"
        for step in trajectory
        if isinstance(step.get("action"), Mapping)
    ]
    if actions:
        lines.append("Actions (offset@speed): " + " -> ".join(actions))
    return "\n".join(lines)


class AgentGraph:
    """Invoke the upstream env-loop graph once per Case."""

    def __init__(self) -> None:
        from app.db.session import create_all_for_local_dev
        from app.modules.agents.registry import get_agent

        # The FastAPI lifespan calls create_all_for_local_dev() before serving. The env
        # loop's persistence hook writes stream rows, so reproduce that startup step;
        # without it every step fails on a missing table and logs a SQLAlchemy traceback
        # into the captured evidence.
        create_all_for_local_dev()
        _trust_run_certificate()
        self._builder = get_agent(AGENT_NAME).builder

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        mission = _mission(value)
        max_steps = int(os.environ.get("LINGJING_MAX_STEPS") or DEFAULT_MAX_STEPS)
        scenario = _scenario(mission)
        graph = self._builder()
        state = await graph.ainvoke(
            {
                "env_name": ENVIRONMENT_NAME,
                "scenario": scenario,
                "max_steps": max_steps,
            }
        )
        return {"answer": _summarise(mission, scenario, state)}

    def close(self):
        self._builder = None


def create_graph():
    return AgentGraph()
