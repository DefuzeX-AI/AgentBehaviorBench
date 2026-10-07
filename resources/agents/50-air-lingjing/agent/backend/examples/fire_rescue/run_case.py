"""\u7a7a\u5730\u534f\u540c\u706d\u706b \u2014 \u7aef\u5230\u7aef\u8dd1\u901a\u5165\u53e3.

\u8c03\u7528\u5f62\u6001:

* ``python examples/fire_rescue/run_case.py``              \u8fdb\u7a0b\u5185 mock world
* ``python examples/fire_rescue/run_case.py --realtime``   \u8d70\u771f\u5b9e WebSocket
  (\u670d\u52a1\u7aef\u8d77 fake LJ-ENGINE \u5ba2\u6237\u7aef\u6a21\u62df UE)

\u6240\u6709\u5171\u4eab\u62bd\u8c61 (``Message`` / ``MessageBus`` / ``GenericAgent`` /
``MultiAgentRuntime`` / ``make_env``) \u90fd\u4ece :mod:`app.modules.envs.*` import,
\u672c\u76ee\u5f55\u53ea\u4fdd\u7559 case \u7279\u6709\u7684 scenario / policy / engine bridge / fake UE.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT))

from app.modules.envs.envs.fire_rescue_env import make_env
from app.modules.envs.multiagent import (
    GenericAgent,
    Message,
    MessageBus,
    MessageContext,
    MultiAgentRuntime,
)
from examples.fire_rescue.engines import MockFireRescueBridge, UEFireRescueBridge
from examples.fire_rescue.policy import build_uav_search_policy, build_ugv_extinguish_policy
from examples.fire_rescue.scenario import build_fire_rescue_scenario, uav_name, ugv_names


RESULTS_DIR = Path(__file__).resolve().parent / "results"


def section(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


async def run_fire_rescue(realtime: bool = False) -> dict[str, Any]:
    scenario = build_fire_rescue_scenario()
    section("[1] \u6784\u9020\u573a\u666f")
    print(f"  \u573a\u666f:  {scenario.sceneName}")
    print(f"  UAV:   {uav_name()}")
    print(f"  UGVs:  {ugv_names()}")
    fire_total = len((scenario.taskMatrix[0].initial_state.model_extra or {}).get("fire_spots", []))
    print(f"  \u706b\u70b9:  {fire_total} \u4e2a (\u4f4d\u7f6e\u4ec5 env \u5185\u90e8\u5df2\u77e5, UAV \u9700 FOV \u63a2\u6d4b)")

    section("[2] \u9009\u62e9\u5f15\u64ce bridge")
    server = None
    fake_ue = None
    if realtime:
        from examples.fire_rescue.fake_engine import FakeUEFireWorld

        server = _spawn_server(9942)
        fake_ue = FakeUEFireWorld("ws://127.0.0.1:9942/ws/LJ-ENGINE/fire-rescue")
        await fake_ue.start()
        bridge = UEFireRescueBridge()
        print("  \u2713 UEFireRescueBridge (WebSocket \u2192 fake UE)")
    else:
        bridge = MockFireRescueBridge()
        print("  \u2713 MockFireRescueBridge (\u8fdb\u7a0b\u5185\u4eff\u771f)")

    section("[3] gym.make \u98ce\u683c\u6784\u9020 env")
    env = make_env(
        "fire_rescue",
        scenario=scenario,
        bridge=bridge,
        evaluator={"name": "fire_rescue_v1"},
        interaction=({"bridge": "realtime"} if realtime else None),
    )
    print(f"  task_id   = {env.task_id}")
    print(f"  bridge    = {env.env.interaction.bridge}")
    print(f"  evaluator = {env.env.evaluator.name}")

    section("[4] \u521b\u5efa\u591a\u667a\u80fd\u4f53 + MessageBus + \u6ce8\u518c\u6d88\u606f\u94a9\u5b50")
    bus = MessageBus()
    uav_agent = GenericAgent(
        name=uav_name(), policy=build_uav_search_policy(uav_name()), bus=bus
    )
    ugv_agents = [
        GenericAgent(name=name, policy=build_ugv_extinguish_policy(name), bus=bus)
        for name in ugv_names()
    ]
    agents = [uav_agent, *ugv_agents]

    print_log: list[str] = []

    def make_logger(agent: GenericAgent):
        async def _log(ctx: MessageContext) -> None:
            print_log.append(
                f"[{agent.name}] \u2190 {ctx.message.sender}/{ctx.message.type}: "
                f"{json.dumps(ctx.message.payload, ensure_ascii=False, default=str)}"
            )
            return None

        return _log

    for agent in agents:
        agent.on_any_message(make_logger(agent))

    @uav_agent.on_message("fire_extinguished")
    async def confirm(ctx: MessageContext) -> Message | None:
        return Message(
            sender=ctx.agent.name,
            type="acknowledged",
            payload={"fire_id": ctx.message.payload.get("fire_id")},
        )

    for ugv in ugv_agents:
        @ugv.on_message("claim_fire")
        async def echo_claim(ctx: MessageContext, _self=ugv) -> Message | None:
            
            claimant = ctx.message.payload.get("claimant")
            if claimant and claimant != _self.name:
                return Message(
                    sender=_self.name,
                    type="yielded",
                    payload={
                        "to": claimant,
                        "fire_id": ctx.message.payload.get("fire_id"),
                    },
                )
            return None

    for agent in agents:
        print(
            f"  \u2713 agent {agent.name}: handlers={list(agent.handlers)}"
            f" + default={'yes' if agent.default_handler else 'no'}"
        )

    section("[5] MultiAgentRuntime \u95ed\u73af")
    runtime = MultiAgentRuntime(env=env, agents=agents, bus=bus, action_key="agents")
    result = await runtime.run(verbose=True)

    section("[6] \u901a\u4fe1\u603b\u7ebf\u5168\u91cf\u56de\u653e (\u524d 15 \u6761)")
    for entry in print_log[:15]:
        print(f"  {entry}")
    if len(print_log) > 15:
        print(f"  ... \u5171 {len(print_log)} \u6761 inbox \u89e6\u53d1\u8bb0\u5f55")

    section("[7] \u6bcf\u4e2a agent \u6536\u53d1\u7edf\u8ba1")
    for name, info in result.per_agent.items():
        s = info["stats"]
        print(f"  {name}: \u53d1{s['sent']:>2} \u6761 / \u6536{s['received']:>2} \u6761 / handlers={s['handlers']}")

    section("[8] \u8bc4\u4f30\u6307\u6807")
    print(json.dumps(result.metrics, indent=2, ensure_ascii=False))
    print(f"  cumulative_reward = {result.cumulative_reward:.3f}")
    print(f"  \u603b\u6d88\u606f\u6570          = {len(result.messages)}")

    section("[9] \u843d\u76d8\u5230 examples/fire_rescue/results/")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _write(RESULTS_DIR / "fire_trajectory.json", [s.__dict__ for s in result.steps])
    _write(
        RESULTS_DIR / "fire_summary.json",
        {
            "task_id": result.task_id,
            "metrics": result.metrics,
            "cumulative_reward": result.cumulative_reward,
            "uav": uav_name(),
            "ugvs": ugv_names(),
            "bridge": env.env.interaction.bridge,
            "message_count": len(result.messages),
        },
    )
    _write(RESULTS_DIR / "fire_messages.json", result.messages)
    _write(RESULTS_DIR / "fire_per_agent.json", result.per_agent)
    sim_rows = _dump_simdata(env.task_id)
    _write(RESULTS_DIR / "fire_simdata_snapshot.json", sim_rows)
    print(f"  fire_trajectory.json        ({len(result.steps)} steps)")
    print(f"  fire_summary.json")
    print(f"  fire_messages.json          ({len(result.messages)} msgs)")
    print(f"  fire_per_agent.json")
    print(f"  fire_simdata_snapshot.json  ({len(sim_rows)} rows)")

    await env.close()
    if fake_ue:
        await fake_ue.stop()
    if server:
        server.stop()
    return {"metrics": result.metrics, "messages": len(result.messages)}


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def _spawn_server(port: int):
    import threading
    import uvicorn

    from app.main import app

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(60):
        if server.started:
            break
        time.sleep(0.1)

    class _Handle:
        def stop(self) -> None:
            server.should_exit = True
            thread.join(timeout=3)

    return _Handle()


def _dump_simdata(task_id: str) -> list[dict[str, Any]]:
    from sqlalchemy import select

    from app.db.models import SimData
    from app.db.session import StreamSessionLocal

    with StreamSessionLocal() as db:
        rows = (
            db.execute(select(SimData).where(SimData.task_id == task_id).order_by(SimData.id))
            .scalars()
            .all()
        )
    return [
        {"id": r.id, "task_id": r.task_id, "data": json.loads(r.data) if r.data else None}
        for r in rows
    ]


def _write(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--realtime", action="store_true", help="\u8d70\u771f\u5b9e WebSocket + fake UE")
    args = parser.parse_args()
    asyncio.run(run_fire_rescue(realtime=args.realtime))


if __name__ == "__main__":
    main()
