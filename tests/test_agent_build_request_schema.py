"""Provider-compatible output still passes the full local contract before saving."""

from copy import deepcopy
import json
from pathlib import Path
from types import SimpleNamespace

from jsonschema import Draft202012Validator
import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.openrouter_provider.request_schema import build_request_schema
from tests.agent_build_fixtures import source, plan, Client, build
from tests.test_agent_build_client import client, response

ROOT = Path(__file__).resolve().parents[1] / "agentbench/onboarding/build_agent_env"
SCHEMAS = ["frameworks/langgraph/assets/planning/response.schema.json", "frameworks/langgraph/assets/manifest/analysis.schema.json",
           "openrouter_provider/assets/file-response.schema.json"]


@pytest.mark.parametrize("path", SCHEMAS)
def test_all_stage_schemas_can_be_sent_without_mutating_the_local_contract(path):
    schema = json.loads((ROOT / path).read_text())
    before = deepcopy(schema)
    instance, requests = client(), []

    def open_request(request, **kwargs):
        requests.append(json.loads(request.data))
        return response({"status": "needs_input"})

    instance.opener = SimpleNamespace(open=open_request)
    instance.generate({"context": {"files": [{"path": "README.md"}]}}, prompt="Analyze.", schema=schema)
    structured = requests[0]["response_format"]["json_schema"]
    wire = structured["schema"]
    Draft202012Validator.check_schema(wire)
    assert structured["strict"] is True
    assert wire["required"] == schema["required"]
    assert wire["additionalProperties"] is False
    assert wire["properties"]["evidence"]["items"]["enum"] == ["README.md"]
    assert schema == before
    assert json.loads((ROOT / path).read_text()) == before
    for keyword in ("if", "then", "else", "pattern", "minLength", "minimum", "maximum"):
        assert f'"{keyword}":' not in json.dumps(wire)
    if "facts" in wire["properties"]:
        assert wire["properties"]["facts"]["anyOf"][1] == {"type": "null"}


def test_projection_walks_schema_positions_not_property_names_or_literal_values():
    schema = {"type": "object", "required": ["if", "pattern"], "additionalProperties": False,
              "properties": {"if": {"$ref": "#/$defs/text"},
                             "pattern": {"enum": [{"if": "literal", "minimum": 1}]}},
              "$defs": {"text": {"type": "string", "pattern": "^ok$", "const": "ok"}}}
    projected = build_request_schema(schema)
    assert projected["properties"] == schema["properties"]
    assert projected["$defs"]["text"] == {"type": "string", "enum": ["ok"]}
    projected["properties"]["pattern"]["enum"][0]["if"] = "changed"
    assert schema["properties"]["pattern"]["enum"][0]["if"] == "literal"


@pytest.mark.parametrize("keyword", ["oneOf", "allOf", "unrecognizedKeyword"])
def test_unhandled_constructs_fail_before_sending_a_weakened_shape(keyword):
    with pytest.raises(BuildError, match="explicit projection"):
        build_request_schema({"type": "object", keyword: []})


def test_conditional_rules_remain_authoritative_in_the_full_schema(plan):
    schema = json.loads((ROOT / SCHEMAS[0]).read_text())
    wire = build_request_schema(schema)
    for invalid in ({**plan, "bindings": []},
                    {**plan, "status": "needs_input", "missing_information": ["Missing entrypoint"]},
                    {**plan, "bindings": ["backend/graph.py:Graph"]}):
        assert Draft202012Validator(wire).is_valid(invalid)
        assert not Draft202012Validator(schema).is_valid(invalid)


@pytest.mark.parametrize("stage", ["plan", "facts"])
@pytest.mark.parametrize("recovers", [True, False])
def test_real_client_responses_require_local_validation_and_bounded_repairs(source, plan, stage, recovers):
    """Only the HTTP boundary is faked; exercise decoding, validation and writes."""
    instance, fixtures, attempts, observed = client(), Client(plan), 0, []

    def open_request(request, **kwargs):
        nonlocal attempts
        body = json.loads(request.data)
        payload = json.loads(body["messages"][1]["content"])
        wire = body["response_format"]["json_schema"]["schema"]
        result = fixtures.generate(payload, prompt="", schema=wire)
        selected = (stage == "plan" and "target_path" not in payload or
                    stage == "facts" and payload.get("target_path") == "agent.toml")
        if selected:
            attempts += 1
            if attempts > 1:
                assert "validation_error" in payload and "previous_response" in payload
            assert not (source.directory / "agent.toml").exists()
            if attempts == 1 or not recovers:
                if stage == "plan":
                    result["bindings"] = []
                else:
                    result["facts"]["tool_routes"] = [{"host_patterns": ["example.test"],
                        "ports": [70000], "methods": ["POST"], "path_patterns": ["/search"]}]
                # The provider accepts this shape; only the full local schema rejects it.
                assert Draft202012Validator(wire).is_valid(result)
        observed.append(payload.get("target_path"))
        return response(result)

    instance.opener = SimpleNamespace(open=open_request)
    if recovers:
        assert build(source, plan, client=instance).status == "generated"
        assert (source.directory / "bindings/bridge.py").is_file()
    else:
        with pytest.raises(BuildError, match="outer binding|response schema"):
            build(source, plan, client=instance)
        assert not (source.directory / "agent.toml").exists()
        assert not (source.directory / "Dockerfile").exists()
        assert observed == ([None, None] if stage == "plan" else [None, "agent.toml", "agent.toml"])
    assert attempts == 2
