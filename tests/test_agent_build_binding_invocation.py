"""Exercise a generated forwarding binding with the real LangGraph loader offline."""

import os
import subprocess
import sys

from tests.agent_build_fixtures import source, plan, build, write


def test_generated_factory_loads_native_graph_and_returns_its_result(source, plan):
    native = '''from typing import TypedDict
from langgraph.graph import StateGraph, START, END

class State(TypedDict):
    message: str
    answer: str

def respond(state):
    return {"answer": state["message"].upper()}

builder = StateGraph(State)
builder.add_node("respond", respond)
builder.add_edge(START, "respond")
builder.add_edge("respond", END)
graph = builder.compile()
'''
    path = write(source.directory, "agent/src/pkg/graph.py", native)
    assert build(source, plan).status == "generated"
    script = '''import sys
from pathlib import Path
from agentbench.adapter.langgraph.config import LangGraphAdapterConfig
from agentbench.adapter.langgraph.loader import load_graph
graph = load_graph(LangGraphAdapterConfig.from_agent_dir(Path(sys.argv[1])))
result = graph.invoke({"message": "binding result"})
assert result["answer"] == "BINDING RESULT", result
'''
    # A fresh process avoids cross-Agent module collisions. Only our local test
    # graph runs; no user source, credentials, network or model call is involved.
    result = subprocess.run([sys.executable, "-B", "-c", script, str(source.directory)],
                            env={**os.environ, "PYTHONPATH": str(source.directory / "agent/src")},
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    assert path.read_text() == native
