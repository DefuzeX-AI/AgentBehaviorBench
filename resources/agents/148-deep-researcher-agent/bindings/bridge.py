"""Run the unmodified native NAT chat/research LangGraph lifecycle.

The public CLI uses load_workflow, one session, and session.run(text), then
runner.result(to_type=str). This binding retains that lifecycle and native
checkpoint history. Its supported headless config disables human clarification,
keeps inline deep research and both Tavily tools, and configures each model via
NAT's normal OpenAI-compatible provider. No prompt or tool is replaced.
"""

import asyncio
from contextlib import AsyncExitStack
from pathlib import Path
import tempfile
import uuid


def deployment_config(source, checkpoint_path):
    """Adapt the shipped operator config without replacing native logic."""
    import yaml
    deployment = yaml.safe_load((source / "configs/config_cli_default.yml").read_text())
    for name, original in deployment["llms"].items():
        deployment["llms"][name] = {
            "_type": "openai",
            "model_name": "gpt-4o",
            "base_url": "https://api.openai.com/v1",
            "api_key": "${OPENAI_API_KEY}",
            "temperature": original["temperature"],
            "top_p": original["top_p"],
            "max_tokens": original["max_tokens"],
            "max_retries": original["num_retries"],
        }
        if "parallel_tool_calls" in original:
            deployment["llms"][name]["parallel_tool_calls"] = original["parallel_tool_calls"]
    deployment["workflow"].update(
        enable_clarifier=False,
        use_async_deep_research=False,
        checkpoint_db=str(checkpoint_path),
    )
    return deployment


class NativeResearcher:
    def __init__(self):
        self._stack = AsyncExitStack()
        self._session = None
        self._closed = False
        self._directory = tempfile.TemporaryDirectory(prefix="abb-deep-researcher-")
        self._conversation_id = str(uuid.uuid4())
        self._sync_runner = None

    async def _start(self):
        import yaml
        from nat.runtime.loader import load_workflow

        source = Path(__file__).resolve().parents[1] / "agent"
        deployment = deployment_config(source, Path(self._directory.name) / "checkpoints.db")
        path = Path(self._directory.name) / "workflow.yml"
        path.write_text(yaml.safe_dump(deployment, sort_keys=False))
        try:
            manager = await self._stack.enter_async_context(load_workflow(str(path)))
            self._session = await self._stack.enter_async_context(manager.session())
        except BaseException:
            await self.aclose()
            raise

    async def ainvoke(self, value, config=None):
        if self._closed:
            raise RuntimeError("The native research session is closed")
        if not isinstance(value, dict) or set(value) != {"message"}:
            raise ValueError("Expected exactly one current text message")
        text = value["message"]
        if not isinstance(text, str) or not text.strip():
            raise ValueError("message must be non-empty text")
        if self._session is None:
            await self._start()
        from langchain_core.runnables.config import var_child_runnable_config
        from nat.builder.context import ContextState

        # Native NAT creates its own RunnableConfig. LangChain's inherited
        # config context preserves live observation callbacks for nested calls;
        # the native CLI's ContextState supplies the conversation checkpoint ID.
        supplied = config or {}
        thread_id = supplied.get("configurable", {}).get("thread_id", self._conversation_id)
        state = ContextState.get()
        conversation_token = state.conversation_id.set(str(thread_id))
        runnable_token = var_child_runnable_config.set(supplied)
        try:
            async with self._session.run(text) as runner:
                response = await runner.result(to_type=str)
            # Match the native CLI's bounded lifecycle boundary: Relay delivers
            # subscriber events asynchronously after the runner returns.
            import logging
            import nemo_relay
            try:
                await nemo_relay.subscribers.flush_async()
            except Exception as error:
                logging.getLogger(__name__).warning("Native Relay flush failed (%s)", type(error).__name__)
            return {"response": response}
        finally:
            var_child_runnable_config.reset(runnable_token)
            state.conversation_id.reset(conversation_token)

    def invoke(self, value, config=None):
        if self._sync_runner is None:
            self._sync_runner = asyncio.Runner()
        return self._sync_runner.run(self.ainvoke(value, config=config))

    async def aclose(self):
        if self._closed:
            return
        self._closed = True
        try:
            await self._stack.aclose()
        finally:
            # NAT caches its SQLite saver without a teardown hook. This path is
            # private to this instance, so release only the saver it owns.
            import sys
            common = sys.modules.get("deep_researcher_agent.common")
            try:
                if common is not None:
                    path = str(Path(self._directory.name) / "checkpoints.db")
                    saver = common._checkpointers.pop(path, None)
                    if saver is not None:
                        await saver.conn.close()
            finally:
                self._directory.cleanup()

    def close(self):
        if self._sync_runner is not None:
            try:
                self._sync_runner.run(self.aclose())
            finally:
                self._sync_runner.close()
                self._sync_runner = None
        elif not self._closed:
            asyncio.run(self.aclose())


def create_graph():
    return NativeResearcher()
