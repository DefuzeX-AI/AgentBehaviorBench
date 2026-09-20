"""Shared offline source and per-file model responses for onboarding tests."""
import copy
import json
import pytest
from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.onboarding.discovery import discover_files
from agentbench.onboarding.source import DownloadedAgent
from agentbench.onboarding.build_agent_env.service import build_agent_environment
from agentbench.sdk.plugin.kuma.plugin import plugin
from tests.kuma_catalog_fixtures import context as catalog_context

URL = "https://github.com/example/my-agent"
REQUIREMENT = """---
agent_description: Echo a supplied message without external services.
input_type: text
strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: TEST-GENERAL
  version: "1"
---
## Production Use Scenario
Return the input text.
## Behaviors to Test
Preserve the supplied message.
## Known Limitations or Prohibited Behaviors
Do not execute input as code.
"""
MANIFEST = """schema_version = "defuzex-bench.agent.v2"
agent_id = "my-agent"
framework = "langgraph"
[runtime]
type = "docker"
execution = "oneshot"
[build]
context = "."
dockerfile = "Dockerfile"
[launch]
argv = ["python", "-m", "agentbench.runtime.agentcontainer.worker"]
[adapter]
type = "langgraph"
config = "langgraph.json"
graph_id = "agent"
input_key = "message"
binding = "bridge.py:create_graph"
"""
DOCKERFILE = """FROM python:3.11-slim
WORKDIR /opt/agent
COPY agent/ ./agent/
COPY .abb-runtime/ /opt/abb-runtime/
COPY agent.toml ./agent.toml
COPY bindings/ ./bindings/
USER agent
"""
BINDING = '''"""Expose the installed upstream graph without changing its behavior."""

def create_graph():
    from pkg.graph import graph
    return graph
'''
FILES = {"agent.toml": MANIFEST, "Dockerfile": DOCKERFILE, "requirement.md": REQUIREMENT,
         "bindings/bridge.py": BINDING,
         ".dockerignore": ".git\n.env\n.env.*\nonboarding/\n"}


def write(root, name, text):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def source(tmp_path, monkeypatch):
    # Replace only live discovery; real profile and catalog validation still run.
    from agentbench.sdk.plugin.kuma import onboarding_catalog
    monkeypatch.setattr(onboarding_catalog, "fetch", lambda **kwargs: catalog_context())
    unit = tmp_path / "resources/agents/01-my-agent"
    write(unit, "agent/langgraph.json", '{"graphs":{"agent":"./src/pkg/graph.py:graph"}}')
    write(unit, "agent/src/pkg/graph.py", 'from pkg import state\nraise AssertionError("never import source")\n')
    write(unit, "agent/src/pkg/state.py", 'from . import tools\nINPUT = "message"\n')
    write(unit, "agent/src/pkg/tools.py", "def search(): pass\n")
    write(unit, "agent/README.md", "A LangGraph message echo Agent.")
    write(unit, "source-manifest.json", json.dumps({"repository": URL, "revision": "abc123"}))
    return DownloadedAgent(unit, URL, "abc123", discover_files(unit / "agent"))


@pytest.fixture
def plan():
    return {"framework": "langgraph", "status": "complete", "summary": "Echo integration", "evidence": ["src/pkg/graph.py"],
            "missing_information": [], "bindings": ["bindings/bridge.py"], "needs_input_schema": False}


class Client:
    def __init__(self, plan, *, files=None, callback=None):
        self.plan = plan
        self.files = dict(FILES if files is None else files)
        self.requests, self.callback = [], callback

    def generate(self, payload, *, prompt, schema):
        self.requests.append(copy.deepcopy(payload))
        if self.callback:
            returned = self.callback(payload)
            if returned is not None:
                return returned
        if "target_path" not in payload:
            return copy.deepcopy(self.plan)
        name = payload["target_path"]
        if payload.get("response_kind") == "configuration_facts":
            manifest = tomllib.loads(self.files[name])
            adapter = manifest["adapter"]
            return {"status": "complete", "summary": "Configuration facts", "evidence": ["src/pkg/graph.py"],
                    "missing_information": [], "path": name, "facts": {
                        "display_name": "My Agent", "framework": manifest["framework"],
                        "adapter": {key: adapter.get(key) for key in
                                    ("config", "graph_id", "input_key", "output_key", "binding")},
                        "env_keys": [], "secret_env_keys": [], "models": [], "tool_routes": [],
                        "input_fields": [{"name": "message", "type": "string", "required": True}]}}
        return {"status": "complete", "summary": "Current file", "evidence": ["src/pkg/graph.py"],
                "missing_information": [], "path": name, "content": self.files[name]}


def build(source, plan, *, client=None, **kwargs):
    return build_agent_environment(source, sdk=plugin, environ=kwargs.pop("environ", {}),
        registry_path=source.directory.parents[1] / "registry.toml", client=client or Client(plan), **kwargs)
