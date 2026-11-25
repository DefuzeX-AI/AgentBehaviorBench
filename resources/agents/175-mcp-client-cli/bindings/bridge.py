"""Bind the native CLI's LangGraph assembly, tools, prompt and SQLite lifecycle.

Only terminal input/output is adapted: ABB supplies the text and receives the
complete final graph state. Native execution errors propagate to ABB.
"""
import asyncio
import os
import uuid
from collections.abc import Mapping
from datetime import datetime


def current_message(value):
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Expected exactly one message field")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Expected a nonempty text message")
    return value


class MCPClientCLIWrapper:
    def __init__(self):
        self._closed = False

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        if self._closed:
            raise RuntimeError("MCP Client CLI agent is closed")
        text = current_message(value)
        from mcp_client_cli import cli as native

        app_config = native.AppConfig.load()
        server_configs = [
            native.McpServerConfig(
                server_name=name,
                server_param=native.StdioServerParameters(
                    command=server.command, args=server.args or [],
                    env={**(server.env or {}), **os.environ},
                ),
                exclude_tools=server.exclude_tools or [],
            )
            for name, server in app_config.get_enabled_servers().items()
        ]
        toolkits, tools = await native.load_tools(server_configs, no_tools=False, force_refresh=False)
        try:
            extra_body = {}
            if app_config.llm.base_url and "openrouter" in app_config.llm.base_url:
                extra_body = {"transforms": ["middle-out"]}
            model = native.init_chat_model(
                model=app_config.llm.model, model_provider=app_config.llm.provider,
                api_key=app_config.llm.api_key, temperature=app_config.llm.temperature,
                base_url=app_config.llm.base_url,
                default_headers={
                    "X-Title": "mcp-client-cli",
                    "HTTP-Referer": "https://github.com/adhikasp/mcp-client-cli",
                },
                extra_body=extra_body,
            )
            prompt = native.ChatPromptTemplate.from_messages([
                ("system", app_config.system_prompt), ("placeholder", "{messages}")
            ]).partial(today_datetime=datetime.now().isoformat())
            manager = native.ConversationManager(native.SQLITE_DB)
            run_config = dict(config or {})
            run_config["configurable"] = {
                "thread_id": uuid.uuid4().hex, "user_id": "myself",
                **run_config.get("configurable", {}),
            }
            run_config.setdefault("recursion_limit", 100)
            async with native.AsyncSqliteSaver.from_conn_string(native.SQLITE_DB) as checkpointer:
                store = native.SqliteStore(native.SQLITE_DB)
                memories = await native.get_memories(store, user_id=run_config["configurable"]["user_id"])
                graph = native.create_react_agent(
                    model, tools, state_schema=native.AgentState, prompt=prompt,
                    checkpointer=checkpointer, store=store,
                )
                state = native.AgentState(
                    messages=[native.HumanMessage(content=text)],
                    today_datetime=datetime.now().isoformat(),
                    memories="\n".join(f"- {memory}" for memory in memories),
                    remaining_steps=3,
                )
                output = native.OutputHandler(text_only=True, only_last_message=True)
                final_state = None
                async for chunk in graph.astream(state, stream_mode=["messages", "values"], config=run_config):
                    if not output.confirm_tool_call(app_config.__dict__, chunk):
                        raise RuntimeError("Native tool confirmation was denied")
                    if isinstance(chunk, tuple) and chunk[0] == "values":
                        final_state = chunk[1]
                if final_state is None:
                    raise RuntimeError("Native graph produced no final state")
                await manager.save_id(run_config["configurable"]["thread_id"], checkpointer.conn)
                return final_state
        finally:
            for toolkit in toolkits:
                await toolkit.close()

    def close(self):
        self._closed = True

    async def aclose(self):
        self.close()


def create_graph():
    return MCPClientCLIWrapper()
