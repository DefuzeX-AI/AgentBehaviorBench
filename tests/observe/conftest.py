import json
from pathlib import Path
from types import SimpleNamespace
import pytest


@pytest.fixture
def offline_agent(tmp_path):
    root = tmp_path / "unit"
    (root / "agent").mkdir(parents=True)
    (root / "agent.toml").write_text('''schema_version = "defuzex-bench.agent.v2"
agent_id = "offline-observe"
[runtime]
type = "docker"
execution = "oneshot"
timeout_sec = 30
env_keys = ["ABB_CONTAINER_TEST"]
[build]
context = "."
dockerfile = "Dockerfile"
[launch]
argv = ["python", "-m", "agentbench.runtime.agentcontainer.worker"]
[adapter]
type = "langgraph"
config = "langgraph.json"
graph_id = "agent"
output_key = "answer"
''')
    (root / "agent" / "langgraph.json").write_text(json.dumps({"graphs": {"agent": "sample.py:graph"}}))
    (root / "agent" / "sample.py").write_text('''import asyncio
import os
from pathlib import Path
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END
class State(TypedDict):
    number: int
    text: str
    answer: str
async def double(state):
    await asyncio.sleep(0)
    if state['number'] < 0:
        raise ValueError('negative input rejected')
    return {'number': state['number'] * 2}
def finish(state, config):
    assert config['configurable']['thread_id']
    if os.environ.get('ABB_CONTAINER_TEST'):
        assert os.getuid() != 0
        for path in ['/opt/agent/agent/sample.py', '/run/abb-input/request.json']:
            try:
                with open(path, 'a') as stream:
                    stream.write('forbidden')
            except OSError:
                pass
            else:
                raise AssertionError('Readonly input/source was writable')
        Path('/run/abb-output/permission-probe').write_text('writable')
    return {'answer': state['text'] + ':' + str(state['number'] + 3)}
builder = StateGraph(State)
builder.add_node('double', double)
builder.add_node('finish', finish)
builder.add_edge(START, 'double')
builder.add_edge('double', 'finish')
builder.add_edge('finish', END)
graph = builder.compile()
''')
    (root / "Dockerfile").write_text('''FROM python:3.11-slim
RUN pip install --no-cache-dir 'langgraph>=1,<2' python-dotenv && useradd -m -u 10001 agent
ENV PYTHONPATH=/opt/abb-runtime
WORKDIR /opt/agent
COPY .abb-runtime /opt/abb-runtime
COPY agent ./agent
COPY agent.toml ./agent.toml
USER agent
''')
    return SimpleNamespace(path=root, agent_id="offline-observe", framework="langgraph")
