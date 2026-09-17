"""ABB message/result boundary for hwchase17/langchain-streamlit-template.

Upstream entrypoint: main.py's load_agent(), the create_react_agent graph the Streamlit page invokes with {"messages": [{"role": "user", ...}]} and a per-session thread id. Importing main.py would run the Streamlit page (and an agent call with its default text), so the binding executes only main.py's imports and the load_agent definition from the file itself. The answer is the last message's content, as the page shows it.
"""
import ast
import asyncio
import uuid
from collections.abc import Mapping
from pathlib import Path

MAIN = Path("/opt/agent/agent/main.py")


def _load_agent():
    tree = ast.parse(MAIN.read_text(encoding="utf-8"))
    keep = [node for node in tree.body
            if isinstance(node, (ast.Import, ast.ImportFrom)) and not any(
                alias.name.startswith("streamlit") for alias in node.names)
            and getattr(node, "module", "") not in {"streamlit", "streamlit_chat"}
            or isinstance(node, ast.FunctionDef) and node.name == "load_agent"]
    namespace = {"__name__": "langchain_streamlit_template_main"}
    exec(compile(ast.Module(body=keep, type_ignores=[]), str(MAIN), "exec"), namespace)
    return namespace["load_agent"]()


class AgentGraph:
    def __init__(self):
        self._graph = _load_agent()
        self._thread = str(uuid.uuid4())

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        output = await self._graph.ainvoke({"messages": [{"role": "user", "content": text}]},
                                           {"configurable": {"thread_id": self._thread}})
        answer = output["messages"][-1].content
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    def close(self):
        self._graph = None


def create_graph():
    return AgentGraph()
