"""Program-owned policy, structured extraction and round-trippable TOML output."""

import json
from types import SimpleNamespace

import pytest

from agentbench.runtime.agentcontainer.config import tomllib
from agentbench.runtime.interception.config import InterceptionConfig
from agentbench.onboarding.build_agent_env.build_toml.encoding import encode_manifest
from agentbench.onboarding.build_agent_env.build_toml.options import ManifestOptions
from agentbench.onboarding.build_agent_env.build_toml.rendering import render_manifest
from agentbench.onboarding.build_agent_env.build_toml.validation import validate_manifest
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, plan, Client, build, write


@pytest.fixture
def facts():
    return {"display_name": "Example Agent", "framework": "langgraph",
            "adapter": {"config": "langgraph.json", "graph_id": "agent", "binding": "bridge.py:create_graph",
                        "input_key": "message", "output_key": None},
            "env_keys": [], "secret_env_keys": ["TAVILY_API_KEY"],
            "models": [{"protocol": "openai-chat", "agent_env": "OPENAI_API_KEY", "endpoint": None}],
            "tool_routes": [{"host_patterns": ["api.tavily.com"], "ports": [443],
                             "methods": ["POST"], "path_patterns": ["/search"]}],
            "input_fields": [{"name": "message", "type": "string", "required": True}]}


def render(source, facts, **kwargs):
    content = render_manifest(facts, source=source, agent_id="my-agent", **kwargs)
    validate_manifest(content, SimpleNamespace(source=source, agent_id="my-agent", plan={"bindings": ["bindings/bridge.py"]}))
    return tomllib.loads(content)


def test_defaults_and_download_provenance_are_program_owned(source, facts):
    write(source.directory, "source-manifest.json", json.dumps({"repository": source.repository,
        "revision": source.revision, "downloaded_on": "2026-09-08"}))
    value = render(source, facts)
    assert value["runtime"]["timeout_sec"] == 300
    assert value["evaluation"]["replay_safe"] is False
    assert "observe" not in value and "context" not in value["adapter"]
    assert value["source"] == {"repository": source.repository, "revision": source.revision,
                               "downloaded_on": "2026-09-08"}
    assert value["launch"]["argv"] == ["python", "-m", "agentbench.runtime.agentcontainer.worker"]


def test_explicit_options_and_mechanical_observe(source, facts):
    options = ManifestOptions(timeout_sec=600, observe=True, adapter_context={"max_search_results": 7})
    value = render(source, facts, options=options)
    assert value["runtime"]["timeout_sec"] == 600
    assert value["adapter"]["context"] == {"max_search_results": 7}
    assert value["observe"]["input_fields"] == [{"name": "message", "label": "message", "required": True}]
    assert "model" not in value["adapter"]["context"]


def test_nested_inputs_use_existing_observe_json_fallback(source, facts):
    facts["input_fields"].append({"name": "schema", "type": "object", "required": True})
    value = render(source, facts, options=ManifestOptions(observe=True))
    assert value["observe"]["input_fields"] == []


def test_gemini_transports_share_one_program_generated_credential(source, facts, tmp_path):
    facts["models"].extend({"protocol": name, "agent_env": "GEMINI_API_KEY", "endpoint": None}
                            for name in ("gemini-content", "gemini-grpc"))
    content = render_manifest(facts, source=source, agent_id="my-agent")
    write(tmp_path, "agent.toml", content)
    interception = InterceptionConfig.from_agent_dir(tmp_path)
    assert len(interception.credentials) == 2 and len(interception.routes) == 3
    assert {route.credential_id for route in interception.routes if route.route_id.startswith("gemini")} == {"gemini"}
    assert interception.tool_routes[0].path_patterns == ("/search",)


def test_custom_model_endpoint_is_preserved_and_validated(source, facts):
    facts["models"][0]["endpoint"] = {"host_patterns": ["model.example.com"], "ports": [8443],
                                      "methods": ["POST"], "path_patterns": ["/api/chat/completions"]}
    assert render(source, facts)["llm_interception"]["routes"][0]["ports"] == [8443]
    facts["models"][0]["endpoint"]["host_patterns"] = ["*"]
    with pytest.raises(ValueError, match="Unsafe interception pattern"):
        render(source, facts)


@pytest.mark.parametrize("field,value", [("runtime", {"timeout_sec": 9999}),
    ("evaluation", {"replay_safe": True}), ("source", {"repository": "https://wrong.example"}),
    ("content", "[evaluation]\nreplay_safe=true"), ("observe", {})])
def test_model_cannot_override_program_policy(source, facts, field, value):
    facts[field] = value
    with pytest.raises(BuildError, match="Invalid manifest facts"):
        render(source, facts)


def test_model_cannot_set_deployment_context(source, facts):
    facts["adapter"]["context"] = {"model": "invented-model"}
    with pytest.raises(BuildError, match="Invalid manifest facts"):
        render(source, facts)


def test_toml_encoding_round_trips_and_prevents_section_injection():
    value = {"display_name": 'Quote " slash \\ newline\n[evaluation]\nreplay_safe=true 中文',
             "adapter": {"context": {"a.b": "literal key", "max": 7, "enabled": True,
                                     "nested": {"list": ["a", "b"]}}},
             "observe": {"input_fields": [{"name": "x", "required": False}]}}
    assert tomllib.loads(encode_manifest(value)) == value


def test_missing_download_date_is_not_invented(source, facts):
    assert "downloaded_on" not in render(source, facts)["source"]


def test_wrong_download_record_is_rejected(source, facts):
    write(source.directory, "source-manifest.json", json.dumps({"repository": source.repository, "revision": "wrong"}))
    with pytest.raises(BuildError, match="revision differs"):
        render(source, facts)


def test_legacy_unit_uses_existing_source_record_without_writing_it(source, facts):
    (source.directory / "source-manifest.json").unlink()
    before = '[source]\nrepository = ' + json.dumps(source.repository) + '\nrevision="abc123"\ndownloaded_on="2026-09-08"\n'
    path = write(source.directory, "agent.toml", before)
    assert render(source, facts)["source"]["downloaded_on"] == "2026-09-08"
    assert path.read_text() == before


def test_old_model_toml_response_is_rejected_then_facts_are_repaired(source, plan):
    calls = 0
    def old_response(payload):
        nonlocal calls
        if payload.get("target_path") == "agent.toml":
            calls += 1
            if calls == 1:
                return {"status": "complete", "summary": "Old response", "evidence": plan["evidence"],
                        "missing_information": [], "path": "agent.toml", "content": "bad TOML"}
            assert "validation_error" in payload and payload["response_kind"] == "configuration_facts"
    client = Client(plan, callback=old_response)
    assert build(source, plan, client=client).status == "generated" and calls == 2
    assert tomllib.loads((source.directory / "agent.toml").read_text())["runtime"]["timeout_sec"] == 300


def test_cli_observe_option_reaches_generated_manifest(source, plan, monkeypatch):
    from agentbench.cli.main import cli
    from agentbench.onboarding import workflow
    from agentbench.onboarding.build_agent_env import service
    monkeypatch.setattr(workflow, "load_project_environment", lambda *args: None)
    monkeypatch.setattr(service, "OpenRouterClient", lambda *args, **kwargs: Client(plan))
    assert cli(["agent", "add", source.repository, "-b", "--with-observe", "--agent-timeout", "450",
                "--agents-dir", str(source.directory.parent), "--registry", str(source.directory.parents[1] / "registry.toml")]) == 0
    value = tomllib.loads((source.directory / "agent.toml").read_text())
    assert value["runtime"]["timeout_sec"] == 450 and value["observe"]["input_fields"][0]["name"] == "message"
