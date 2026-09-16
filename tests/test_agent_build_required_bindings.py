"""A complete generated integration always keeps its outer binding in the image."""

import json
from types import SimpleNamespace

import pytest

from agentbench.onboarding.build_agent_env.build_blinding.validation import validate_binding
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
from tests.agent_build_fixtures import source, plan, Client, FILES, MANIFEST, build, write


def test_empty_complete_plan_is_repaired_before_generating_files(source, plan):
    attempts = 0

    def callback(payload):
        nonlocal attempts
        if "target_path" not in payload:
            attempts += 1
            if attempts == 1:
                return {**plan, "bindings": []}
            assert "must include an outer binding" in payload["validation_error"]
            assert not (source.directory / "agent.toml").exists()

    assert build(source, plan, client=Client(plan, callback=callback)).status == "generated"
    assert attempts == 2
    assert (source.directory / "bindings/bridge.py").read_text() == FILES["bindings/bridge.py"]


def test_repeated_empty_plan_never_creates_partial_configuration(source, plan):
    with pytest.raises(BuildError, match="must include an outer binding"):
        build(source, plan, client=Client({**plan, "bindings": []}))
    assert not (source.directory / "agent.toml").exists()


def test_manifest_cannot_bypass_binding_with_a_compatible_native_graph(source, plan):
    files = {**FILES, "agent.toml": MANIFEST.replace('binding = "bridge.py:create_graph"\n', "")}
    with pytest.raises(BuildError, match="response schema"):
        build(source, plan, client=Client(plan, files=files))
    assert not (source.directory / "agent.toml").exists()


def test_manifest_cannot_select_an_unplanned_existing_binding(source, plan):
    write(source.directory, "bindings/other.py", FILES["bindings/bridge.py"])
    files = {**FILES, "agent.toml": MANIFEST.replace("bridge.py:create_graph", "other.py:create_graph")}
    with pytest.raises(BuildError, match="plan.bindings"):
        build(source, plan, client=Client(plan, files=files))


def test_missing_binding_in_manual_manifest_is_reported_without_overwriting(source, plan):
    manual = MANIFEST.replace('binding = "bridge.py:create_graph"\n', "")
    path = write(source.directory, "agent.toml", manual)
    client = Client(plan)
    result = build(source, plan, client=client)
    assert result.status == "conflict" and "requires adapter.binding" in result.messages[0]
    assert path.read_text() == manual
    assert [request.get("target_path") for request in client.requests] == [None]


def test_invalid_cached_plan_is_replanned_and_files_are_revalidated(source, plan):
    first = build(source, plan)
    state_path = first.attempt.parent / "build-state.json"
    state = json.loads(state_path.read_text())
    state["plan"]["bindings"] = []
    state_path.write_text(json.dumps(state))
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert [request.get("target_path") for request in client.requests] == [None]


def test_failed_binding_keeps_manifest_and_resumes_at_binding(source, plan):
    files = {**FILES, "bindings/bridge.py": "async def create_graph(): return object()\n"}
    with pytest.raises(BuildError, match="synchronous factory"):
        build(source, plan, client=Client(plan, files=files))
    assert (source.directory / "agent.toml").exists()
    assert not (source.directory / "bindings/bridge.py").exists()
    assert not (source.directory / "Dockerfile").exists()
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert [request.get("target_path") for request in client.requests] == [
        "bindings/bridge.py", "Dockerfile", "requirement.md"]


@pytest.mark.parametrize("content,reason", [
    ("def another_factory(): return graph", "selected export"),
    ("async def create_graph(): return graph", "synchronous factory"),
    ("def create_graph(value): return value", "without arguments"),
    ("def create_graph(*, company): return company", "without arguments"),
    ("def create_graph(): yield graph", "not a generator"),
    ("@some_decorator\ndef create_graph(): return graph", "undecorated"),
    ("class Bridge:\n async def ainvoke(self, value): yield value\ndef create_graph(): return Bridge()",
     "not yield an async iterator"),
])
def test_factory_contract_errors_are_found_without_imports(content, reason):
    session = SimpleNamespace(completed={"agent.toml": MANIFEST}, current_path="bindings/bridge.py")
    with pytest.raises(BuildError, match=reason):
        validate_binding(content, session)


def test_final_unit_validation_rechecks_a_manually_changed_binding(source, plan):
    build(source, plan)
    write(source.directory, "bindings/bridge.py", "def create_graph(required): return required")
    with pytest.raises(BuildError, match="without arguments"):
        validate_unit(source.directory, plugin)
