"""ABB message/result boundary for tablegpt/tablegpt-agent.

Upstream entrypoint: tablegpt.agent.create_tablegpt_graph(llm, pybox_manager, ...), wired as in examples/data_analysis.py: a ChatOpenAI client for the TableGPT2 model, AsyncLocalPyBoxManager with the packaged IPython profile to execute generated analysis code, MemorySaver and one sandbox session per Case. The input follows examples/quick_start.py (messages, parent_id, date); the answer is the final message's text.
"""
import asyncio
import shutil
import tempfile
from pathlib import Path
import uuid
from collections.abc import Mapping
from datetime import date


def _text(message):
    content = getattr(message, "content", message.get("content") if isinstance(message, Mapping) else message)
    if isinstance(content, list):
        content = "".join(part.get("text", "") if isinstance(part, Mapping) else str(part) for part in content)
    return content if isinstance(content, str) else str(content)


class AgentGraph:
    def __init__(self):
        from langchain_openai import ChatOpenAI
        from langgraph.checkpoint.memory import MemorySaver
        from pybox import AsyncLocalPyBoxManager
        from tablegpt import DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR
        from tablegpt.agent import create_tablegpt_graph

        self._session = str(uuid.uuid4())
        if not DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR:
            raise RuntimeError('TableGPT local kernel profile is not installed')
        self._profile = tempfile.TemporaryDirectory(prefix='abb-tablegpt-')
        profile = Path(self._profile.name) / 'profile'
        try:
            shutil.copytree(DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR, profile, copy_function=shutil.copyfile)
            self._manager = AsyncLocalPyBoxManager(profile_dir=str(profile))
            self._graph = create_tablegpt_graph(
                llm=ChatOpenAI(model_name="TableGPT2-7B"),
                pybox_manager=self._manager,
                checkpointer=MemorySaver(),
                session_id=self._session,
            )
        except BaseException:
            self._profile.cleanup()
            raise

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        from langchain_core.messages import HumanMessage

        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        state = {"messages": [HumanMessage(content=text)], "parent_id": str(uuid.uuid4()), "date": date.today()}
        run_config = dict(config or {})
        run_config['configurable'] = dict(run_config.get('configurable') or {})
        run_config['configurable'].setdefault('thread_id', self._session)
        result = await self._graph.ainvoke(state, config=run_config)
        messages = result.get("messages", []) if isinstance(result, Mapping) else []
        answer = _text(messages[-1]) if messages else None
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    async def aclose(self):
        if self._graph is None:
            return
        self._graph = None
        try:
            await self._manager.shutdown_all(now=True)
        finally:
            self._profile.cleanup()

    def close(self):
        asyncio.run(self.aclose())


def create_graph():
    return AgentGraph()
