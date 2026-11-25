"""Invoke the full native research workflow; retain its human approval nodes."""
import asyncio
import os
from pathlib import Path
import shutil
import threading
import uuid


class NativeBinding:
    def invoke(self, value, config=None):
        import yaml
        root = Path("/opt/agent/agent")
        deployment = Path.home()/"datagen-config"
        shutil.copytree(root/"config", deployment, dirs_exist_ok=True)
        model_path = deployment/"agent_models.yaml"
        models = yaml.safe_load(model_path.read_text())
        for settings in models["agents"].values():
            settings["provider"] = "openai"
            settings["model_config"] = {
                **settings["model_config"], "model": "gpt-4o-mini",
                "base_url": "https://api.openai.com/v1",
            }
        model_path.write_text(yaml.safe_dump(models))
        os.environ["CONFIG_DIRECTORY"] = str(deployment)
        os.environ["WORKING_DIRECTORY"] = "/workspace"
        os.environ["CHROMEDRIVER_PATH"] = "/usr/bin/chromedriver"
        os.environ.setdefault("USER_AGENT", "MultiAgentDataAnalysis/1.0")
        os.chdir("/workspace")
        from src.core.mcp_manager import get_mcp_manager
        from src.core.state import create_initial_state
        from src.system import MultiAgentSystem

        loop = asyncio.new_event_loop()
        def run_loop():
            asyncio.set_event_loop(loop)
            loop.run_forever()
        thread = threading.Thread(target=run_loop, daemon=True)
        thread.start()
        manager = get_mcp_manager()
        manager._main_loop = loop
        try:
            native = MultiAgentSystem()
            run_config = dict(config or {})
            run_config["configurable"] = {**run_config.get("configurable", {}), "thread_id": uuid.uuid4().hex}
            run_config["recursion_limit"] = 3000
            text = value.get("message", "") if isinstance(value, dict) else str(value)
            return native.workflow_manager.get_graph().invoke(create_initial_state(text), config=run_config)
        finally:
            try:
                asyncio.run_coroutine_threadsafe(manager.close_all(), loop).result(timeout=20)
            finally:
                loop.call_soon_threadsafe(loop.stop)
                thread.join(timeout=2)

    async def ainvoke(self, value, config=None):
        return await asyncio.to_thread(self.invoke, value, config)


def create_graph():
    return NativeBinding()
