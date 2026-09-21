"""ABB message/result boundary for KRATSZ/LabScript-AI.

Upstream entrypoint: backend.pylabrobot_agent.create_pylabrobot_agent(), the generate -> simulate -> feedback loop that run_pylabrobot_agent_and_stream_events drives with a user_query and a hardware configuration. The binding loads the default hardware profile (load_hardware_configuration()) and passes the Case Input as user_query; the answer is the generated PyLabRobot protocol code and the final outcome.
"""
import asyncio
import json
from collections.abc import Mapping


class AgentGraph:
    def __init__(self):
        from backend.pylabrobot_agent import create_pylabrobot_agent, generate_dynamic_pylabrobot_knowledge
        from backend.pylabrobot_utils import load_hardware_configuration

        self._app = create_pylabrobot_agent()
        self._hardware = load_hardware_configuration()
        self._knowledge = generate_dynamic_pylabrobot_knowledge(self._hardware)

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        state = {"user_query": text, "hardware_config": self._hardware,
                 "pylabrobot_knowledge": self._knowledge, "attempts": 0,
                 "max_attempts": 2, "force_regenerate": False}
        # The simulator node is async-only, so the graph must be driven with ainvoke.
        final = await self._app.ainvoke(state, {"recursion_limit": 50})
        code = final.get("python_code") if isinstance(final, Mapping) else None
        if not isinstance(code, str) or not code.strip():
            raise RuntimeError("Agent returned no protocol code")
        outcome = final.get("final_outcome") if isinstance(final, Mapping) else None
        sim = final.get("simulation_result") if isinstance(final, Mapping) else None
        return {"answer": f"Outcome: {outcome}\n\nProtocol code:\n{code}" +
                (f"\n\nSimulation: {json.dumps(sim, default=str)[:1000]}" if sim else "")}

    def close(self):
        self._app = None


def create_graph():
    return AgentGraph()
