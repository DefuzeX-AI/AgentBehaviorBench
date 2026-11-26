"""Invoke Curie's complete native graph, preserving clarification and tools."""
import asyncio
import importlib
import json
import os
from pathlib import Path
import sys
import uuid


class NativeCurie:
    def invoke(self, value, config=None):
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        os.chdir("/curie")
        if "/curie" not in sys.path:
            sys.path.insert(0, "/curie")
        os.environ.update(MODEL="openai/gpt-4o-mini", RUNTIME="local")
        run = uuid.uuid4().hex
        logs = Path("/logs")/run
        logs.mkdir(parents=True)
        question = logs/"question.txt"
        question.write_text(text)
        deployment = json.loads(Path("configs/base_config.json").read_text())
        deployment.update(unique_id=run, iteration=1, codebase_dir="", base_dir="/all",
            log_filename=f"logs/{run}/curie.log", exp_plan_filename=f"logs/{run}/question.txt")
        path = logs/"config.json"
        path.write_text(json.dumps(deployment))
        # The native code tool resolves ../workspace/config.toml from /curie.
        import toml
        Path("/workspace/config.toml").write_text(toml.dumps({
            "core": {"runtime": "local", "file_store": "local", "max_iterations": 30},
            "llm": {"model": "openai/gpt-4o-mini", "api_key": os.environ["OPENAI_API_KEY"],
                    "base_url": "https://api.openai.com/v1"},
        }))
        Path("/workspace/config.toml").chmod(0o600)
        previous = sys.argv
        try:
            sys.argv = ["construct_workflow_graph.py", str(path)]
            native = importlib.import_module("construct_workflow_graph")
            graph, metadata, native_config = native.build_graph(native.State, str(path))
        finally:
            sys.argv = previous
        metadata.put(("admin", "exp-sched"), "question", text)
        return graph.invoke({"messages": [("user", text)], "is_terminate": False,
            "is_user_input_done": not native_config.get("is_user_interrupt_allowed", False)},
            config={"recursion_limit": native_config.get("max_global_steps", 20) + native.settings.CONCLUDER_BUFFER_STEPS,
                    "configurable": {"thread_id": "main_graph_id"}})

    async def ainvoke(self, value, config=None):
        return await asyncio.to_thread(self.invoke, value, config)


def create_graph():
    return NativeCurie()
