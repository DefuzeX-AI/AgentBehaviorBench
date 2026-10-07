"""\u7aef\u5230\u7aef\u8dd1\u901a\u5165\u53e3 \u2014 \u7528 Gym-style API \u5b8c\u6210\u591a\u673a\u914d\u9001\u4efb\u52a1.

\u652f\u6301\u4e24\u79cd\u8c03\u5ea6\u6a21\u5f0f:

* ``--mode multi`` (\u9ed8\u8ba4) **\u591a\u667a\u80fd\u4f53 + \u901a\u4fe1\u603b\u7ebf**.
  \u6bcf\u67b6\u65e0\u4eba\u673a\u4e00\u4efd ``GenericAgent`` + ``SingleDronePolicy``, \u5171\u4eab ``MessageBus``.
  \u6bcf\u8f6e:
    1) \u6bcf\u4e2a agent \u5904\u7406\u4e0a\u4e00\u8f6e\u6536\u5230\u7684\u6d88\u606f (\u53ef\u89e6\u53d1\u7528\u6237\u6ce8\u518c\u7684 ``@on_message`` \u56de\u8c03);
    2) \u6bcf\u4e2a agent \u770b\u81ea\u5bb6\u89c2\u6d4b + \u521a\u6536\u5230\u7684\u6d88\u606f, \u51b3\u7b56\u672c\u673a\u52a8\u4f5c (\u53ef\u987a\u5e26\u5e7f\u64ad\u6d88\u606f);
    3) runtime \u628a N \u67b6\u52a8\u4f5c\u6c47\u603b\u540e\u9001\u5165 env.step.

* ``--mode central`` \u65e7\u7684\u96c6\u4e2d\u5f0f\u7b56\u7565 (\u4e00\u6b21\u6027\u7ed9\u6240\u6709\u65e0\u4eba\u673a\u51fa\u52a8\u4f5c), \u7559\u4f5c\u5bf9\u6bd4.

\u5f15\u64ce\u5207\u6362:

* ``--realtime`` \u5207\u5230 ``UEMultiDroneBridge``, \u670d\u52a1\u7aef\u8d77\u4e00\u4e2a fake UE \u5ba2\u6237\u7aef\u8d70\u771f WS.
* \u9ed8\u8ba4\u8d70 ``MockMultiDroneBridge`` (\u8fdb\u7a0b\u5185\u4eff\u771f).

\u6240\u6709\u5171\u4eab\u62bd\u8c61 (``Message`` / ``MessageBus`` / ``GenericAgent`` /
``MultiAgentRuntime``) \u90fd\u6765\u81ea\u9879\u76ee\u4e3b\u6846\u67b6 :mod:`app.modules.envs.multiagent`,
\u672c\u76ee\u5f55\u53ea\u4fdd\u7559 case \u7279\u5b9a\u7684 scenario / policy / engine bridge.
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

from app.modules.envs.envs.multi_drone_delivery_env import make_env
from app.modules.envs.multiagent import (
    GenericAgent,
    Message,
    MessageBus,
    MessageContext,
    MultiAgentRuntime,
)
from examples.full_case.engines import MockMultiDroneBridge, UEMultiDroneBridge
from examples.full_case.policy import build_delivery_policy, build_single_drone_policy
from examples.full_case.scenario import build_delivery_scenario, fleet_names


RESULTS_DIR = Path(__file__).resolve().parent / "results"


def section(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
async def run_multi_agent(realtime: bool = False) -> dict[str, Any]:
    # from app.modules.envs.scenario import ScenarioSpec
    # scenario = ScenarioSpec.from_file("app/modules/envs/scenarios/multi_drone_delivery.yaml")
    scenario = build_delivery_scenario()
    fleet = fleet_names()
    section("[1] \u591a\u667a\u80fd\u4f53\u6a21\u5f0f \u2014 \u6784\u9020\u573a\u666f")
    print(f"  \u573a\u666f: {scenario.sceneName}")
    print(f"  \u7f16\u961f: {fleet}")

    section("[2] \u9009\u62e9\u5f15\u64ce bridge")
    server = None
    fake_ue = None
    if realtime:
        from examples.full_case.fake_engine import FakeUEFleet

        server = _spawn_server(9933)
        fake_ue = FakeUEFleet("ws://127.0.0.1:9933/ws/LJ-ENGINE/fleet-demo")
        await fake_ue.start()
        bridge = UEMultiDroneBridge()
        print("  \u2713 UEMultiDroneBridge (WebSocket \u2192 fake UE)")
    else:
        bridge = MockMultiDroneBridge()
        print("  \u2713 MockMultiDroneBridge (\u8fdb\u7a0b\u5185\u4eff\u771f)")

    section("[3] gym.make \u98ce\u683c\u6784\u9020 env")
    env = make_env(
        "multi_drone_delivery",
        scenario=scenario,
        bridge=bridge,
        evaluator={"name": "delivery_v1"},
        interaction=({"bridge": "realtime"} if realtime else None),
    )
    print(f"  task_id            = {env.task_id}")
    print(f"  bridge             = {env.env.interaction.bridge}")
    print(f"  evaluator          = {env.env.evaluator.name}")

    section("[4] \u521b\u5efa\u591a\u667a\u80fd\u4f53 + MessageBus + \u6ce8\u518c\u6d88\u606f\u5904\u7406\u56de\u8c03")
    bus = MessageBus()
    agents = [
        GenericAgent(name=name, policy=build_single_drone_policy(name), bus=bus)
        for name in fleet
    ]

    print_log: list[str] = []

    def make_logger(agent: GenericAgent):
        async def _log(ctx: MessageContext) -> None:
            print_log.append(
                f"[{agent.name}] \u2190 {ctx.message.sender}/{ctx.message.type}: "
                f"{json.dumps(ctx.message.payload, ensure_ascii=False)}"
            )
            return None

        return _log

    for agent in agents:
        agent.on_any_message(make_logger(agent))

    @agents[0].on_message("delivered")
    async def cheer(ctx: MessageContext) -> Message | None:
        return ctx.message.reply(
            "cheer",
            {"from": ctx.agent.name, "text": f"\u606d\u559c {ctx.message.sender} \u5b8c\u6210\u6295\u9012!"},
        )

    @agents[1].on_message("approaching_goal")
    async def standby(ctx: MessageContext) -> Message | None:
        return Message(
            sender=ctx.agent.name,
            type="standby",
            payload={"observer": ctx.agent.name, "monitor": ctx.message.sender},
        )

    for agent in agents:
        print(
            f"  \u2713 agent {agent.name}: handlers={list(agent.handlers)} + "
            f"default={'yes' if agent.default_handler else 'no'}"
        )

    section("[5] MultiAgentRuntime \u95ed\u73af")
    runtime = MultiAgentRuntime(env=env, agents=agents, bus=bus, action_key="drones")
    result = await runtime.run(verbose=True)

    section("[6] \u901a\u4fe1\u603b\u7ebf\u5168\u91cf\u56de\u653e (\u987a\u5e8f)")
    for entry in print_log[:12]:
        print(f"  {entry}")
    if len(print_log) > 12:
        print(f"  ... \u5171 {len(print_log)} \u6761 inbox \u89e6\u53d1\u8bb0\u5f55")

    section("[7] \u6bcf\u4e2a agent \u7684\u6536\u53d1\u7edf\u8ba1")
    for name, info in result.per_agent.items():
        s = info["stats"]
        print(f"  {name}: \u53d1{s['sent']:>2} \u6761 / \u6536{s['received']:>2} \u6761 / handlers={s['handlers']}")

    section("[8] \u8bc4\u4f30\u6307\u6807")
    print(json.dumps(result.metrics, indent=2, ensure_ascii=False))
    print(f"  cumulative_reward = {result.cumulative_reward:.3f}")
    print(f"  \u603b\u6d88\u606f\u6570          = {len(result.messages)}")

    section("[9] \u843d\u76d8\u5230 examples/full_case/results/")
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    _write(RESULTS_DIR / "multi_agent_trajectory.json", [s.__dict__ for s in result.steps])
    _write(
        RESULTS_DIR / "multi_agent_summary.json",
        {
            "task_id": result.task_id,
            "metrics": result.metrics,
            "cumulative_reward": result.cumulative_reward,
            "fleet": fleet,
            "bridge": env.env.interaction.bridge,
            "message_count": len(result.messages),
        },
    )
    _write(RESULTS_DIR / "messages.json", result.messages)
    _write(RESULTS_DIR / "per_agent.json", result.per_agent)
    sim_rows = _dump_simdata(env.task_id)
    _write(RESULTS_DIR / "simdata_snapshot.json", sim_rows)
    print(f"  multi_agent_trajectory.json  ({len(result.steps)} steps)")
    print(f"  multi_agent_summary.json")
    print(f"  messages.json                ({len(result.messages)} msgs)")
    print(f"  per_agent.json")
    print(f"  simdata_snapshot.json        ({len(sim_rows)} rows)")

    await env.close()
    if fake_ue:
        await fake_ue.stop()
    if server:
        server.stop()

    return {"metrics": result.metrics, "messages": len(result.messages)}


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
async def run_central(realtime: bool = False) -> dict[str, Any]:
    scenario = build_delivery_scenario()
    section("[central] \u5355 policy \u7edf\u7ba1\u6240\u6709\u65e0\u4eba\u673a (\u4f5c\u4e3a\u5bf9\u7167)")
    bridge: Any
    server = None
    fake_ue = None
    if realtime:
        from examples.full_case.fake_engine import FakeUEFleet

        server = _spawn_server(9933)
        fake_ue = FakeUEFleet("ws://127.0.0.1:9933/ws/LJ-ENGINE/fleet-demo")
        await fake_ue.start()
        bridge = UEMultiDroneBridge()
    else:
        bridge = MockMultiDroneBridge()
    env = make_env(
        "multi_drone_delivery",
        scenario=scenario,
        bridge=bridge,
        evaluator={"name": "delivery_v1"},
        interaction=({"bridge": "realtime"} if realtime else None),
    )
    obs, info = await env.reset()
    policy = build_delivery_policy()
    while True:
        action = await policy.act(obs, env.scenario, env.history)
        obs, reward, terminated, truncated, info = await env.step(action)
        if terminated or truncated:
            break
    print(json.dumps(env.metrics, indent=2, ensure_ascii=False))
    print(f"cumulative_reward = {env.cumulative_reward:.3f}")
    await env.close()
    if fake_ue:
        await fake_ue.stop()
    if server:
        server.stop()
    return {"metrics": env.metrics}


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
    parser.add_argument(
        "--mode",
        choices=["multi", "central"],
        default="multi",
        help="multi=\u6bcf\u67b6\u65e0\u4eba\u673a\u4e00\u4e2a agent + \u901a\u4fe1\u603b\u7ebf; central=\u5355 policy \u7edf\u7ba1",
    )
    parser.add_argument("--realtime", action="store_true", help="\u8d70\u771f\u5b9e WebSocket + fake UE")
    args = parser.parse_args()

    if args.mode == "multi":
        asyncio.run(run_multi_agent(realtime=args.realtime))
    else:
        asyncio.run(run_central(realtime=args.realtime))


if __name__ == "__main__":
    main()
