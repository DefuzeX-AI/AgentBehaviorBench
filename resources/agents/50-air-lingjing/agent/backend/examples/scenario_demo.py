"""\u7aef\u5230\u7aef\u7528\u6237\u6d4b\u8bd5\u6848\u4f8b (\u5355\u6587\u4ef6\u53ef\u8dd1).

\u6f14\u793a\u5185\u5bb9
========
1. \u7528 ``ScenarioDefinition`` \u7c7b\u628a"\u60f3\u5b9a"\u5199\u6210 Python \u4ee3\u7801\u3002
2. \u628a\u5b83\u8f6c\u6210 ``ScenarioSpec``, \u8ba9\u6846\u67b6\u81ea\u52a8\u5206\u914d\u5317\u4eac\u65f6\u95f4 task_id\u3002
3. \u901a\u8fc7 HTTP \u5728 ``open_vocab_navigation`` \u73af\u5883\u91cc\u5f00 episode (\u9ed8\u8ba4 mock bridge)\u3002
4. \u540c\u65f6\u6f14\u793a *\u771f\u5b9e WebSocket* \u8def\u5f84: \u542f\u52a8\u4e00\u4e2a\u4e34\u65f6\u7684 fake LJ-ENGINE \u5ba2\u6237\u7aef,
   \u8ba2\u9605 ``/ws/LJ-ENGINE/...``, \u7528 ``resetScenario / getObservation /
   executeAction`` \u4e09\u4e2a\u547d\u4ee4\u5b8c\u6210\u89c2\u6d4b-\u52a8\u4f5c\u5f80\u8fd4, \u5168\u8fc7\u7a0b\u90fd\u7528 episode \u7684
   task_id \u843d\u5e93\u5230 ``sim_data``.
5. \u624b\u52a8 step / \u81ea\u52a8 run / \u7528 LangGraph \u95ed\u73af agent \u4e09\u79cd\u8c03\u7528\u90fd\u8dd1\u4e00\u6b21,
   \u6700\u540e\u7528 ``SELECT * FROM sim_data WHERE task_id = ?`` \u628a\u8fd9\u6b21\u4efb\u52a1
   \u7684\u5b9e\u65f6\u6570\u636e\u5168\u90e8\u62c9\u51fa\u6765\u6253\u5370, \u9a8c\u8bc1\u53ef\u6309\u4efb\u52a1 id \u533a\u5206.

\u8fd0\u884c\u65b9\u5f0f
========
::

    cd python-lingjing-ai-server
    .venv/bin/python -m pip install websockets   # fake engine \u7528
    .venv/bin/python examples/scenario_demo.py

\u811a\u672c\u4f1a\u81ea\u5df1\u5728\u5b50\u8fdb\u7a0b\u91cc\u62c9\u8d77 uvicorn, \u7528\u5b8c\u5173\u6389;
\u6ca1\u6709 AI API key \u4e5f\u80fd\u8dd1, \u7b56\u7565\u4f1a\u81ea\u52a8\u56de\u9000\u5230\u542f\u53d1\u5f0f\u52a8\u4f5c.
"""

from __future__ import annotations

import asyncio
import json
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

import httpx
import uvicorn
from sqlalchemy import select

from app.db.models import SimData
from app.db.session import StreamSessionLocal
from app.modules.envs.scenario_models import (
    DroneEntity,
    EquipmentList,
    GoalPosition,
    InitialState,
    Position,
    ScenarioDefinition,
    TaskMatrixItem,
)
from app.modules.envs.task_id import beijing_now

HTTP_PORT = 9921
BASE_URL = f"http://127.0.0.1:{HTTP_PORT}"
WS_URL = f"ws://127.0.0.1:{HTTP_PORT}/ws/LJ-ENGINE/demo-engine"


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def build_definition() -> ScenarioDefinition:
    """\u5b8c\u5168\u7528 Python \u4ee3\u7801\u5199\u4e00\u4e2a "\u4fa6\u5bdf_\u7a7a\u5730\u534f\u540c" \u60f3\u5b9a (Individual \u4efb\u52a1)."""

    return ScenarioDefinition(
        sceneName="\u4fa6\u5bdf_\u7a7a\u5730\u534f\u540c_DEMO",
        collaborationType="\u7a7a\u5730\u534f\u540c",
        sceneRegion="\u516c\u56ed\u533a\u57df",
        equipmentList=EquipmentList(
            droneEntityList=[
                DroneEntity(
                    equipmentCode="DRONE-001",
                    name="drone1",
                    data=Position(X=0.0, Y=0.0, Z=50.0),
                    raw=30.0,
                    sensorType="EO/IR",
                )
            ]
        ),
        taskMatrix=[
            TaskMatrixItem(
                taskLevel="Individual",
                task_id="DEMO_TASK_001",
                goal="\u65e0\u4eba\u673a\u5de1\u68c0\u5e76\u62b5\u8fd1\u76ee\u6807\u70b9",
                initial_state=InitialState(
                    weather="Clear",
                    traffic="None",
                    goalPosition=GoalPosition(lon=80.0, lat=0.0, alt=50.0),
                ),
            )
        ],
    )


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
class FakeEngineClient:
    """\u8ba2\u9605 /ws/LJ-ENGINE/demo-engine, \u5bf9 reset / observe / action \u7ed9\u51fa
    \u6700\u7b80\u5355\u7684\u4e16\u754c\u6a21\u578b: \u65e0\u4eba\u673a\u6bcf\u6536\u5230\u4e00\u6b21 executeAction \u5c31\u6309 offset \u79fb\u52a8."""

    def __init__(self) -> None:
        self.pose = {"x": 0.0, "y": 0.0, "z": 50.0}
        self.goal = {"x": 80.0, "y": 0.0, "z": 50.0}
        self._task: asyncio.Task | None = None
        self.connected = asyncio.Event()
        self.received: list[dict] = []

    async def _run(self) -> None:
        import websockets

        async with websockets.connect(WS_URL) as ws:
            await ws.recv()  
            self.connected.set()
            while True:
                raw = await ws.recv()
                envelope = json.loads(raw)
                data = envelope.get("data") or {}
                if isinstance(data, list):
                    data = data[0] if data else {}
                command_type = data.get("commandType")
                request_id = data.get("request_id") or data.get("requestId")
                self.received.append({"commandType": command_type, "task_id": data.get("taskId")})

                if command_type == "resetScenario":
                    scenario = data.get("scenario") or {}
                    drones = (scenario.get("equipmentList") or {}).get("droneEntityList") or []
                    if drones:
                        d = drones[0].get("data") or {}
                        self.pose = {
                            "x": float(d.get("X", 0)),
                            "y": float(d.get("Y", 0)),
                            "z": float(d.get("Z", 0)),
                        }
                    task_matrix = scenario.get("taskMatrix") or []
                    if task_matrix:
                        gp = (task_matrix[0].get("initial_state") or {}).get("goalPosition") or {}
                        self.goal = {
                            "x": float(gp.get("lon", 0)),
                            "y": float(gp.get("lat", 0)),
                            "z": float(gp.get("alt", 0)),
                        }
                    await ws.send(json.dumps({
                        "commandType": "sceneResetAck",
                        "request_id": request_id,
                        "data": {"status": "reset", "pose": self.pose, "goal": self.goal},
                    }))

                elif command_type == "getObservation":
                    distance = ((self.pose["x"] - self.goal["x"]) ** 2
                                + (self.pose["y"] - self.goal["y"]) ** 2) ** 0.5
                    await ws.send(json.dumps({
                        "commandType": "observationResponse",
                        "request_id": request_id,
                        "data": {
                            "pose": dict(self.pose),
                            "goal_position": dict(self.goal),
                            "distance": distance,
                            "camera_rgb": "",
                            "minimap": "",
                        },
                    }))

                elif command_type == "executeAction":
                    action = data.get("action") or {}
                    offset = action.get("offset") or [0, 0]
                    if isinstance(offset, list) and len(offset) >= 2:
                        self.pose["x"] += float(offset[0])
                        self.pose["y"] += float(offset[1])
                    elif isinstance(offset, dict):
                        self.pose["x"] += float(offset.get("x", 0))
                        self.pose["y"] += float(offset.get("y", 0))
                    if request_id:
                        await ws.send(json.dumps({
                            "commandType": "actionAck",
                            "request_id": request_id,
                            "data": {"ok": True, "pose": dict(self.pose)},
                        }))

    async def start(self) -> None:
        self._task = asyncio.create_task(self._run())
        try:
            await asyncio.wait_for(self.connected.wait(), timeout=5.0)
        except asyncio.TimeoutError as exc:
            raise RuntimeError("fake LJ-ENGINE \u672a\u80fd\u5728 5s \u5185\u5efa\u94fe\u5230\u670d\u52a1\u5668") from exc

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except BaseException:
                pass


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
class _ServerThread:
    """\u540e\u53f0\u7ebf\u7a0b\u8dd1 uvicorn, \u4e0d\u963b\u585e\u4e3b\u6d41\u7a0b."""

    def __init__(self) -> None:
        from app.main import app

        config = uvicorn.Config(app, host="127.0.0.1", port=HTTP_PORT, log_level="warning")
        self.server = uvicorn.Server(config)
        import threading

        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def start(self) -> None:
        self.thread.start()
        for _ in range(50):
            if self.server.started:
                return
            time.sleep(0.1)
        raise RuntimeError("uvicorn \u542f\u52a8\u8d85\u65f6")

    def stop(self) -> None:
        self.server.should_exit = True
        self.thread.join(timeout=3)


# --------------------------------------------------------------------------- #

# --------------------------------------------------------------------------- #
def section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


async def demo_with_mock_bridge() -> str:
    """\u6f14\u793a mock bridge \u8def\u5f84 (\u4e0d\u4f9d\u8d56\u771f\u5b9e\u5f15\u64ce)."""

    section("[1] mock bridge \u2014 \u901a\u8fc7 HTTP \u521b\u5efa episode (\u9ed8\u8ba4 bridge=mock)")

    definition = build_definition()
    payload = definition.to_engine_payload()
    print("ScenarioDefinition.to_engine_payload() \u9884\u89c8 (\u5c06\u771f\u5b9e\u4e0b\u53d1\u7ed9 LJ-ENGINE \u7684\u5b57\u6bb5):")
    print(json.dumps(payload, ensure_ascii=False, indent=2)[:400] + " ...")

    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        body = {"definition": definition.model_dump(exclude_none=True), "task_index": 0}
        resp = (await client.post("/api/envs/open_vocab_navigation/episodes", json=body)).json()
        assert resp["code"] == 200, resp
        data = resp["data"]
        task_id = data["task_id"]
        print("\n\u521b\u5efa\u6210\u529f:")
        print(f"  task_id            = {task_id}")
        print(f"  episode_id         = {data['episode_id']}")
        print(f"  created_at_beijing = {data['created_at_beijing']}")
        init_obs = data["initial_observation"]
        print(f"  initial pose       = {init_obs.get('pose')}")
        print(f"  initial distance   = {init_obs.get('distance'):.2f}")

        section("[2] mock bridge \u2014 \u624b\u52a8 step \u4e00\u6b21")
        step = (await client.post(
            f"/api/envs/episodes/{task_id}/step",
            json={"action": {"offset": [20.0, 0.0], "speed": 25}},
        )).json()["data"]
        print(f"  reward             = {step['reward']:.4f}")
        print(f"  next pose          = {step['observation']['pose']}")
        print(f"  cumulative_reward  = {step['cumulative_reward']:.4f}")

        section("[3] mock bridge \u2014 /run \u8ba9\u9ed8\u8ba4 LLM \u7b56\u7565\u81ea\u52a8\u8dd1\u5230\u7ec8\u6b62")
        run = (await client.post(
            f"/api/envs/episodes/{task_id}/run", json={"max_steps": 15}
        )).json()["data"]
        print(f"  trajectory length  = {len(run['trajectory'])}")
        print(f"  cumulative_reward  = {run['cumulative_reward']:.4f}")
        print(f"  final metrics      = {run.get('metrics')}")
        print(f"  status             = {run.get('status')}")

    return task_id


async def demo_with_realtime_bridge() -> str | None:
    """\u6f14\u793a bridge=realtime \u8def\u5f84: \u60f3\u5b9a JSON \u771f\u7684\u901a\u8fc7 WebSocket \u4e0b\u53d1\u5230 fake UE."""

    section("[4] realtime bridge \u2014 \u542f\u52a8 fake LJ-ENGINE \u5ba2\u6237\u7aef")
    engine = FakeEngineClient()
    try:
        await engine.start()
    except Exception as exc:
        print(f"  [\u8df3\u8fc7] \u65e0\u6cd5\u542f\u52a8 fake engine (\u53ef\u80fd\u672a\u5b89\u88c5 websockets): {exc}")
        return None
    print("  fake LJ-ENGINE \u5df2\u5efa\u94fe, \u7b49\u5f85 resetScenario / getObservation / executeAction ...")

    definition = build_definition()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=15.0) as client:
        body = {
            "definition": definition.model_dump(exclude_none=True),
            "interaction": {
                "bridge": "realtime",
                "action": {"require_ack": False, "timeout_sec": 2.0},
                "observation": {"timeout_sec": 3.0},
            },
        }
        resp = (await client.post("/api/envs/open_vocab_navigation/episodes", json=body)).json()
        if resp.get("code") != 200:
            print(f"  [\u8df3\u8fc7] realtime \u8def\u5f84\u4e0d\u53ef\u7528: {resp.get('message')}")
            await engine.stop()
            return None
        data = resp["data"]
        task_id = data["task_id"]
        print(f"  task_id        = {task_id}")
        print(f"  bridge         = {data['resolved_interaction']['bridge']}")
        print(f"  engine \u6536\u5230\u547d\u4ee4 = {[r['commandType'] for r in engine.received]}")

        section("[5] realtime bridge \u2014 \u901a\u8fc7 WS \u6765\u56de step 3 \u6b21")
        for i in range(3):
            step = (await client.post(
                f"/api/envs/episodes/{task_id}/step",
                json={"action": {"offset": [20.0, 0.0], "speed": 25}},
            )).json()["data"]
            obs = step["observation"]
            print(f"  step {i + 1}: pose={obs.get('pose')}  "
                  f"distance={obs.get('distance', 0):.2f}  reward={step['reward']:.3f}")

        await client.delete(f"/api/envs/episodes/{task_id}")

    await engine.stop()
    print(f"  fake engine \u6700\u7ec8\u7d2f\u8ba1\u6536\u5230 {len(engine.received)} \u6761\u547d\u4ee4")
    return task_id


async def demo_with_agent_invoke() -> str:
    """\u6f14\u793a\u901a\u8fc7 /api/agents/{name}/invoke \u8c03\u7528 LangGraph \u95ed\u73af agent."""

    section("[6] LangGraph \u95ed\u73af agent \u2014 POST /api/agents/open_vocab_navigation_env_loop/invoke")
    definition = build_definition()
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=20.0) as client:
        resp = (await client.post(
            "/api/agents/open_vocab_navigation_env_loop/invoke",
            json={
                "env_name": "open_vocab_navigation",
                "scenario": definition.model_dump(exclude_none=True),
                "max_steps": 10,
            },
        )).json()
        assert resp["code"] == 200, resp
        data = resp["data"]
        trajectory = data.get("trajectory") or []
        print(f"  episode_id         = {data['episode_id']}")
        print(f"  trajectory length  = {len(trajectory)}")
        if "cumulative_reward" in data:
            print(f"  cumulative reward  = {data['cumulative_reward']:.4f}")
        print(f"  final metrics      = {data.get('metrics')}")
        return data["episode_id"]


def query_sim_data(task_id: str) -> None:
    section(f"[\u67e5\u8be2] task_id={task_id} \u7684 sim_data (\u5b9e\u65f6\u6570\u636e\u6309\u4efb\u52a1\u9694\u79bb)")
    with StreamSessionLocal() as db:
        rows = db.execute(
            select(SimData).where(SimData.task_id == task_id).order_by(SimData.id)
        ).scalars().all()
    print(f"  \u672c\u4efb\u52a1\u5171\u5199\u5165 {len(rows)} \u884c\u5b9e\u65f6\u6570\u636e")
    phase_counter: dict[str, int] = {}
    for row in rows:
        try:
            payload = json.loads(row.data or "{}")
        except Exception:
            payload = {}
        phase = payload.get("phase", "?")
        phase_counter[phase] = phase_counter.get(phase, 0) + 1
    print(f"  \u6309 phase \u7edf\u8ba1: {phase_counter}")
    if rows:
        sample = json.loads(rows[0].data)
        sample_text = json.dumps(sample, ensure_ascii=False)
        print(f"  \u7b2c\u4e00\u884c\u6837\u4f8b (\u622a\u65ad): {sample_text[:240]}...")


async def main() -> None:
    server = _ServerThread()
    server.start()
    try:
        print(f"uvicorn \u5df2\u5728 {BASE_URL} \u542f\u52a8")
        print(f"\u6f14\u793a\u8fd0\u884c\u65f6\u95f4 (Beijing): {beijing_now().isoformat()}")

        mock_task = await demo_with_mock_bridge()
        query_sim_data(mock_task)

        try:
            rt_task = await demo_with_realtime_bridge()
        except Exception as exc:
            print(f"\n[realtime demo] \u5f02\u5e38: {exc}")
            rt_task = None
        if rt_task:
            query_sim_data(rt_task)

        try:
            agent_task = await demo_with_agent_invoke()
            query_sim_data(agent_task)
        except Exception as exc:
            print(f"\n[agent invoke] \u8df3\u8fc7 (LangGraph \u6ce8\u518c\u540d\u53ef\u80fd\u4e0e\u672c\u5730\u4e0d\u540c): {exc}")

        section("DEMO \u7ed3\u675f")
        print("\u5982\u9700\u624b\u52a8\u6838\u5bf9, \u53ef\u7528 sqlite3 \u76f4\u63a5\u67e5:")
        print(f"  sqlite3 data/stream.db \"SELECT * FROM sim_data WHERE task_id = '{mock_task}';\"")
    finally:
        server.stop()


if __name__ == "__main__":
    asyncio.run(main())
