"""Run langrepl's native general graph with Case-owned history and resources.

The native graph, tools, subagents and approval rules are retained. Its model
configuration selects the native OpenAI-compatible client for ABB replacement
interception, including delegation and compression. CLI rendering,
slash commands and CLI-only automatic compression are outside this graph boundary.
"""
import asyncio
from collections.abc import Mapping
from contextlib import AsyncExitStack, asynccontextmanager
from datetime import datetime
from pathlib import Path
from uuid import uuid4


class LangreplGraph:
    def __init__(self, working_dir=None):
        self.working_dir = Path(working_dir or "/workspace/langrepl")
        self._graph = None
        self._initializer = None
        self._cleanup = None
        self._closed = False
        self._loop = None
        self._runner = None
        self._thread_id = str(uuid4())
        self._resources = AsyncExitStack()
        self._mcp = None

    async def _start(self):
        if self._closed:
            raise RuntimeError("langrepl binding is closed")
        loop = asyncio.get_running_loop()
        if self._loop is not None and self._loop is not loop:
            raise RuntimeError("Use one event loop for langrepl initialization, calls and cleanup")
        self._loop = loop
        if self._graph is None:
            from langrepl.cli.bootstrap.initializer import Initializer

            self.working_dir.mkdir(parents=True, exist_ok=True)
            self._initializer = Initializer()
            # Native create_graph acquires MCP and SQLite before compiling. Its
            # cleanup callback is returned only on success. Keep ownership of
            # those same resources if compilation or cancellation fails midway.
            create_checkpointer = self._initializer.checkpointer_factory.create
            create_mcp = self._initializer.mcp_factory.create

            @asynccontextmanager
            async def owned_checkpointer(*args, **kwargs):
                yield await self._resources.enter_async_context(create_checkpointer(*args, **kwargs))

            async def owned_mcp(*args, **kwargs):
                self._mcp = await create_mcp(*args, **kwargs)
                return self._mcp

            self._initializer.checkpointer_factory.create = owned_checkpointer
            self._initializer.mcp_factory.create = owned_mcp
            try:
                self._agent_config = await self._initializer.load_agent_config(None, self.working_dir)
                self._configure_models()
                self._graph, self._cleanup = await self._initializer.create_graph(
                    None, None, self.working_dir
                )
            except BaseException:
                await self.aclose()
                raise

    def _configure_models(self):
        from langrepl.configs.llm import LLMProvider

        # LLMConfig is the native deployment configuration, not Agent logic.
        # The registry returns this cached config to create_graph. Retain its
        # generation limits and use the native Chat Completions client.
        # ABB replacement interception supplies the effective destination,
        # credentials and model; this source-side model label is a placeholder.
        def compatible(config):
            return config.model_copy(update={
                "provider": LLMProvider.OPENAI, "model": "abb-runtime-selected",
                "extended_reasoning": None, "provider_options": None,
                "input_cost_per_mtok": None, "output_cost_per_mtok": None,
            })

        agent = self._agent_config
        agent.llm = compatible(agent.llm)
        for subagent in agent.subagents or ():
            subagent.llm = compatible(subagent.llm)
        if agent.compression and agent.compression.llm:
            agent.compression.llm = compatible(agent.compression.llm)

    def _sync(self, operation):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Use ainvoke/aclose from an active event loop")
        if self._runner is None:
            self._runner = asyncio.Runner()
        return self._runner.run(operation())

    def invoke(self, value, config=None):
        return self._sync(lambda: self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        from langchain_core.messages import AIMessage, HumanMessage
        from langgraph.types import Command
        from langrepl.agents.context import AgentContext
        from langrepl.cli.builders import MessageContentBuilder
        from langrepl.configs import ApprovalMode
        from langrepl.core.constants import OS_VERSION, PLATFORM

        # Validate before allocating native asynchronous resources. JSON-looking
        # text remains text; only explicit structured Inputs can resume interrupts.
        if isinstance(value, Mapping) and set(value) == {"resume"}:
            state = Command(resume=value["resume"])
        elif isinstance(value, Command):
            state = value
        elif isinstance(value, Mapping) and "messages" in value:
            state = dict(value)
        else:
            text = value.get("message") if isinstance(value, Mapping) else value
            if not isinstance(text, str) or not text.strip():
                raise ValueError("Supply text, {message: text}, native messages, or an explicit resume")
            content, references = MessageContentBuilder(self.working_dir).build(text)
            state = {"messages": [HumanMessage(
                content=content, short_content=text,
                additional_kwargs={"reference_mapping": references},
            )]}

        await self._start()
        cfg = dict(config or {})
        cfg["configurable"] = dict(cfg.get("configurable") or {})
        cfg["configurable"].setdefault("thread_id", self._thread_id)
        cfg.setdefault("recursion_limit", self._agent_config.recursion_limit)
        llm = self._agent_config.llm
        context = AgentContext(
            approval_mode=ApprovalMode.SEMI_ACTIVE,
            working_dir=self.working_dir,
            platform=PLATFORM,
            os_version=OS_VERSION,
            current_date_time_zoned=datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z"),
            user_memory=await self._initializer.load_user_memory(self.working_dir),
            tool_catalog=self._initializer.cached_tools_in_catalog,
            skill_catalog=self._initializer.cached_agent_skills,
            input_cost_per_mtok=llm.input_cost_per_mtok,
            output_cost_per_mtok=llm.output_cost_per_mtok,
            tool_output_max_tokens=(self._agent_config.tools.output_max_tokens
                                    if self._agent_config.tools else None),
        )
        native = await self._graph.ainvoke(state, config=cfg, context=context)
        interrupts = native.get("__interrupt__", ())
        if interrupts:
            response = "Tool approval required; the requested action has not completed. " + "; ".join(
                str(item.value) for item in interrupts
            )
        else:
            response = next((message.content for message in reversed(native.get("messages", ()))
                             if isinstance(message, AIMessage)), "")
        return {"response": response, "state": native}

    async def aclose(self):
        if self._closed:
            return
        if self._loop is not None and self._loop is not asyncio.get_running_loop():
            raise RuntimeError("Close langrepl on the event loop that initialized it")
        self._closed = True
        cleanup, self._cleanup = self._cleanup, None
        try:
            if cleanup is not None:
                await cleanup()
            elif self._mcp is not None:
                await self._mcp.close()
        finally:
            try:
                await self._resources.aclose()
            finally:
                self._graph = None
                self._mcp = None

    def close(self):
        if self._closed and self._runner is None:
            return
        # Reject async callers before entering the runner-disposal path.
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError("Use ainvoke/aclose from an active event loop")
        try:
            self._sync(self.aclose)
        finally:
            runner, self._runner = self._runner, None
            if runner is not None:
                runner.close()


def create_graph():
    return LangreplGraph()
