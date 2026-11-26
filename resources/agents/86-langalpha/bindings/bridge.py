"""Run the native PTC agent with a real, pinned local SSH computer."""
import asyncio
import os
from pathlib import Path
import uuid


class NativeBinding:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI
        from ptc_agent import PTCAgent
        from ptc_agent.config.loaders import load_from_files
        from ptc_agent.config.core import SSHConfig
        from ptc_agent.core.session import Session
        from ptc_agent.core.sandbox.providers.ssh import set_client_key_loader

        root = Path("/opt/agent/agent")
        native = await load_from_files(root / "agent_config.yaml", search_paths=False)
        client = ChatOpenAI(model="gpt-4o-mini", base_url="https://api.openai.com/v1")
        native.llm_client = client
        native.subsidiary_llm_clients = {
            role: client.model_copy()
            for role in ["compaction", "fetch", *["subagent:" + name for name in native.subagents.enabled]]
        }
        native.fallback_llm_clients = [client.model_copy() for _ in (native.llm.fallback or [])]
        native.fallback_llm_names = ["gpt-4o-mini"] * len(native.fallback_llm_clients)
        core = native.to_core_config()
        # The upstream ComputerManager uses this per-computer overlay for SSH.
        core.sandbox.provider = "ssh"
        state = Path(os.environ["HOME"]) / "abb-ssh"
        core.sandbox.ssh = SSHConfig(
            host="127.0.0.1", port=2222, username="agent", os="Linux",
            host_key=(state / "host.pub").read_text().strip(),
            key_owner="abb-local-computer", allow_private_addresses=True,
            login_from=["127.0.0.1"], trusted_host=False,
        )

        async def load_key(owner):
            if owner != "abb-local-computer":
                raise ValueError("Unknown SSH computer key owner")
            return (state / "client").read_text()

        set_client_key_loader(load_key)
        session = Session("ABB native greeting", core)
        try:
            await session.initialize()
            thread = uuid.uuid4().hex
            graph = PTCAgent(native).create_agent(
                session.sandbox, session.mcp_registry, session=session, thread_id=thread,
            )
            run_config = dict(config or {})
            run_config["configurable"] = {**run_config.get("configurable", {}), "thread_id": thread}
            text = value.get("message", "") if isinstance(value, dict) else str(value)
            return await graph.ainvoke({"messages": [HumanMessage(content=text)]}, config=run_config)
        finally:
            await session.cleanup()
            set_client_key_loader(None)


def create_graph():
    import runpy
    runpy.run_path("/opt/agent/bootstrap/start.py", run_name="abb_deployment")
    return NativeBinding()
