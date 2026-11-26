"""Invoke MATE's native session, RBAC, guardrail and multi-agent execution boundary."""
import asyncio
import os
from pathlib import Path
import sys
import uuid


class NativeBinding:
    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        from shared.utils.langgraph.session_store import get_session_store
        from shared.utils.langgraph.runner import run_sse_stream
        from shared.utils.langgraph import agent_builder
        import json

        app_name = "chess_mate_root"
        # The native RBAC layer creates the local ordinary user and checks roles.
        user_id = "abb-" + uuid.uuid4().hex
        session = get_session_store().create_session(app_name, user_id)
        if not session:
            raise RuntimeError("Native MATE session creation failed")
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        events, replies = [], []
        try:
            async for frame in run_sse_stream(app_name, user_id, session["id"],
                                              {"role": "user", "parts": [{"text": text}]}):
                for block in frame.split("\n\n"):
                    if not block.startswith("data:"):
                        continue
                    event = json.loads(block[5:])
                    events.append(event)
                    if event.get("error_code") or event.get("error_message"):
                        raise RuntimeError("Native MATE run failed: " + str(event.get("error_message")))
                    if not event.get("partial") and event.get("content", {}).get("role") == "model":
                        parts = event["content"].get("parts", [])
                        if any(part.get("functionCall", {}).get("name") == "adk_request_confirmation" for part in parts):
                            raise RuntimeError("Native MATE requires human confirmation")
                        replies.extend(part["text"] for part in parts if part.get("text"))
            if not replies:
                raise RuntimeError("Native MATE returned no assistant reply")
            return {"reply": "\n".join(replies), "events": events}
        finally:
            checkpointer = agent_builder._checkpointer
            if checkpointer is not None and hasattr(checkpointer, "conn"):
                await checkpointer.conn.close()
                agent_builder._checkpointer = None


def create_graph():
    sys.path.insert(0, "/opt/agent/agent")
    os.chdir("/opt/agent/agent")
    os.environ["DB_TYPE"] = "sqlite"
    os.environ["DB_PATH"] = str(Path.home()/"mate.db")
    os.environ["AGENT_FRAMEWORK"] = "langgraph"
    os.environ["PLAYWRIGHT_BROWSERS_PATH"] = "/opt/playwright"
    from shared.utils.database_client import get_database_client
    from shared.utils.models import AgentConfig
    database = get_database_client()
    session = database.get_session()
    if session is None:
        raise RuntimeError("Native MATE database initialization failed")
    try:
        agents = session.query(AgentConfig).all()
        if not any(agent.name == "chess_mate_root" for agent in agents):
            raise RuntimeError("Native MATE default chess agent was not seeded")
        for agent in agents:
            agent.model_name = "openai/gpt-4o-mini"
        session.commit()
    finally:
        session.close()
    return NativeBinding()
