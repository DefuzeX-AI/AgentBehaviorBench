import importlib.util
import json
import sys
import tomllib
from pathlib import Path

import pytest

from agentbench.harness.registry import load_registry


ROOT = Path(__file__).parents[1]
UNIT = ROOT / "resources" / "agents" / "57-omniwriter"
REPOSITORY = "https://github.com/twanew/OmniWriter"
REVISION = "2d0aedc00552795bfa366fcbc123888042493dea"


def _binding():
    name = "issue381_omniwriter_binding"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(
        name, UNIT / "bindings" / "omniwriter_bridge.py"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def test_source_registry_and_runtime_are_pinned_for_issue381():
    manifest = tomllib.loads((UNIT / "agent.toml").read_text())
    source = json.loads((UNIT / "source-manifest.json").read_text())
    registration = load_registry(ROOT / "resources" / "registry.toml").find(
        "omniwriter", enabled_only=False
    )

    assert manifest["source"] == {
        "repository": REPOSITORY,
        "revision": REVISION,
        "downloaded_on": "2026-10-16",
        "method": "git",
    }
    assert source["repository"] == REPOSITORY
    assert source["revision"] == REVISION
    assert registration.path == UNIT
    assert registration.status == "adapting"
    assert registration.enabled is False
    assert registration.max_steps == 1
    assert manifest["runtime"]["timeout_sec"] == 1800


def test_binding_uses_production_orchestrator_not_upstream_test_graph():
    text = (UNIT / "bindings" / "omniwriter_bridge.py").read_text()
    manifest = tomllib.loads((UNIT / "agent.toml").read_text())

    assert "src.pipeline.orchestrator import WriterAgentOrchestrator" in text
    assert "from src.pipeline.state_model import MessageState" in text
    assert "builtins.MessageState = MessageState" in text
    assert "test/search_user_agent.py" not in text
    assert manifest["adapter"]["binding"] == "omniwriter_bridge.py:create_graph"
    assert "graph_id" not in manifest["adapter"]


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("write about retrieval", ("write about retrieval", None, None, False)),
        (
            {
                "topic": "write about retrieval",
                "demand": "concise",
                "thread_id": "case-381",
                "is_lookup_outline": True,
            },
            ("write about retrieval", "concise", "case-381", True),
        ),
    ],
)
def test_boundary_preserves_native_input_fields(value, expected):
    assert _binding().request_from_input(value) == expected


def test_native_prompt_compatibility_preserves_json_and_fills_declared_slots():
    template = '{\n  "route_to": "title_decomposer"\n}\nTopic: {{ user_query }}'
    escaped = _binding()._escape_native_format_template(template, ("user_query",))

    assert escaped.format(user_query="retrieval") == (
        '{\n  "route_to": "title_decomposer"\n}\nTopic: retrieval'
    )


def test_locked_elasticsearch_compatibility_drops_only_retired_timeout(monkeypatch):
    module = _binding()
    calls = []

    class FakeESModule:
        @staticmethod
        def Elasticsearch(*args, **kwargs):
            calls.append((args, kwargs))
            return "client"

    monkeypatch.setattr(module.importlib, "import_module", lambda name: FakeESModule)
    module._install_elasticsearch_compatibility()

    assert FakeESModule.Elasticsearch("host", timeout=180, request_timeout=180) == "client"
    assert calls == [(('host',), {"request_timeout": 180})]


def test_elasticsearch_wait_requires_a_listening_http_socket(monkeypatch):
    module = _binding()

    class RunningProcess:
        returncode = None

        @staticmethod
        def poll():
            return None

    ticks = iter((0.0, 0.0, 2.0))
    monkeypatch.setattr(module.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(
        module.socket,
        "create_connection",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ConnectionRefusedError()),
    )

    with pytest.raises(TimeoutError):
        module._wait_for_elasticsearch(RunningProcess(), timeout=1)

    class ListeningSocket:
        closed = False

        def close(self):
            self.closed = True

    listening = ListeningSocket()
    monkeypatch.setattr(module.time, "monotonic", lambda: 0.0)
    monkeypatch.setattr(
        module.socket, "create_connection", lambda *_args, **_kwargs: listening
    )
    module._wait_for_elasticsearch(RunningProcess(), timeout=1)
    assert listening.closed is True


@pytest.mark.parametrize(
    "value",
    ["", "   ", {}, {"topic": "x", "invented": True}, {"topic": "x", "thread_id": ""}],
)
def test_boundary_rejects_invalid_or_invented_input(value):
    with pytest.raises(ValueError):
        _binding().request_from_input(value)


def test_embedded_elasticsearch_and_network_are_explicit():
    dockerfile = (UNIT / "Dockerfile").read_text()
    binding = (UNIT / "bindings" / "omniwriter_bridge.py").read_text()
    rules = tomllib.loads((UNIT / "network" / "rules.toml").read_text())
    route = rules["tool_routes"][0]

    assert "docker.elastic.co/elasticsearch/elasticsearch:9.3.0" in dockerfile
    assert "elasticsearch-plugin install --batch analysis-icu" in dockerfile
    assert "USER agent" in dockerfile
    assert "AWS_EC2_METADATA_DISABLED" in binding
    assert "-Xms256m -Xmx256m" in binding
    assert "-Expack.ml.enabled=false" in binding
    assert route["host_patterns"] == ["127.0.0.1"]
    assert route["ports"] == [9200]
    assert route["path_patterns"] == ["/", "/default_index*"]
    assert {"HEAD", "GET", "POST", "PUT", "DELETE"} <= set(route["methods"])


def test_manifest_declares_only_real_external_routes_and_secrets():
    manifest = tomllib.loads((UNIT / "agent.toml").read_text())
    runtime = manifest["runtime"]
    interception = manifest["llm_interception"]

    assert runtime["secret_env_keys"] == ["EMBEDDING_BASE_API_KEY", "TAVILY_API_KEY"]
    assert interception["credentials"][0]["agent_env"] == "LLM_BASE_API_KEY"
    assert interception["network_config"] == "network/rules.toml"
    tool_hosts = {
        host
        for route in interception["tool_routes"]
        for host in route["host_patterns"]
    }
    assert tool_hosts == {"api.tavily.com", "ark.cn-beijing.volces.com"}


def test_requirement_matches_the_native_branch_topology():
    requirement = (UNIT / "requirement.md").read_text()

    assert "not an automatic final stage" in requirement
    assert "article_post_process" in requirement
    assert "1,800-second execution window" in requirement
    assert "finishes with polishing" not in requirement


def test_restored_source_keeps_license_and_real_topology():
    snapshot = UNIT / "agent"
    if not snapshot.is_dir():
        pytest.skip("Requires the source-manifest checkout")

    assert (snapshot / "LICENSE").is_file()
    orchestrator = (snapshot / "src" / "pipeline" / "orchestrator.py").read_text()
    assert 'builder.add_edge("assemble_article_node", END)' in orchestrator
    assert 'builder.add_edge("deepagents_node", END)' in orchestrator
    assert 'builder.add_edge("assemble_article_node", "deepagents_node")' not in orchestrator


def test_unit_ships_every_outer_build_input_without_secrets():
    for relative in (
        "README.md",
        "requirement.md",
        "Dockerfile",
        ".dockerignore",
        "agent.toml",
        "source-manifest.json",
        "bindings/omniwriter_bridge.py",
        "network/rules.toml",
    ):
        assert (UNIT / relative).is_file(), relative
    assert not any(path.name == ".env" for path in UNIT.rglob("*"))
    assert "/resources/agents/*/agent/" in (ROOT / ".gitignore").read_text()
