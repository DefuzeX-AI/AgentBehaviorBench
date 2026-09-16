"""Distinguish existing native symbols from new outer binding files."""

import json

from jsonschema import Draft202012Validator
import pytest

from agentbench.onboarding.build_agent_env.planning.service import ASSETS
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from tests.agent_build_fixtures import source, plan, Client, build


@pytest.mark.parametrize("reference", ["backend/graph.py:Graph", "langgraph_entry.py:graph",
    "backend/nodes/grounding.py:GroundingNode", "bindings/bridge.py:create_graph",
    "../bindings/bridge.py", "bindings/nested/bridge.py"])
def test_provider_schema_rejects_symbols_and_non_binding_paths(plan, reference):
    schema = json.loads((ASSETS / "response.schema.json").read_text())
    plan["bindings"] = [reference]
    assert list(Draft202012Validator(schema).iter_errors(plan))


def test_plan_correction_explains_path_vs_symbol_and_can_resume(source, plan):
    calls = 0

    def wrong_then_correct(payload):
        nonlocal calls
        if "target_path" not in payload:
            calls += 1
            if calls == 1:
                return {**plan, "bindings": ["backend/graph.py:Graph"]}
            message = payload["validation_error"]
            assert "bindings/bridge.py" in message
            assert "source entrypoint" in message
            assert "Every complete plan needs an outer binding" in message

    client = Client(plan, callback=wrong_then_correct)
    assert build(source, plan, client=client).status == "generated"
    assert calls == 2
    assert (source.directory / "bindings/bridge.py").is_file()


def test_repeated_source_symbols_do_not_create_files_or_registration(source, plan):
    wrong = {**plan, "bindings": ["backend/graph.py:Graph", "backend/nodes/editor.py:Editor"]}
    with pytest.raises(BuildError, match="source entrypoint"):
        build(source, plan, client=Client(wrong))
    assert not (source.directory / "agent.toml").exists()
    assert not (source.directory.parents[1] / "registry.toml").exists()
