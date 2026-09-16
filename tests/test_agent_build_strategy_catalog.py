"""Live SDK context reaches generation and constrains the saved requirement."""

import json

import pytest

from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.common.records import records_directory
from agentbench.sdk.plugin.kuma import onboarding_catalog
from tests.agent_build_fixtures import source, plan, Client, FILES, REQUIREMENT, build
from tests.kuma_catalog_fixtures import context


def test_full_catalog_is_fetched_once_and_reaches_every_request(source, plan, monkeypatch):
    calls = []
    snapshot = context()

    def fetch(**kwargs):
        calls.append(kwargs)
        return snapshot

    monkeypatch.setattr(onboarding_catalog, "fetch", fetch)
    client = Client(plan)
    result = build(source, plan, client=client)
    assert result.status == "generated" and len(calls) == 1
    assert calls[0]["timeout"] > 0
    assert all(request["sdk_context"] == snapshot for request in client.requests)
    assert json.loads((result.attempt / "sdk-context.json").read_text()) == snapshot
    assert not (source.directory / "sdk-context.json").exists()


def test_catalog_failure_stops_before_model_requests_and_does_not_use_cache(source, plan, monkeypatch):
    build(source, plan)

    def unavailable(**kwargs):
        raise ValueError("Catalog refresh unavailable")

    monkeypatch.setattr(onboarding_catalog, "fetch", unavailable)
    client = Client(plan)
    with pytest.raises(BuildError, match="Catalog refresh unavailable"):
        build(source, plan, client=client)
    assert client.requests == []
    assert (source.directory / "requirement.md").read_text() == REQUIREMENT


@pytest.mark.parametrize("identifier,version", [
    ("MADE-UP-GROUP", "1"), ("TEST-RESEARCH", "1"),
    ("TEST-UNAVAILABLE", "1"), ("TEST-WRITES", "1"),
])
def test_invalid_selection_repairs_only_requirement_using_same_catalog(source, plan, identifier, version):
    calls = 0

    def bad_first(payload):
        nonlocal calls
        if payload.get("target_path") == "requirement.md":
            calls += 1
            assert payload["sdk_context"] == context()
            if calls == 1:
                text = REQUIREMENT.replace("TEST-GENERAL", identifier).replace('version: "1"', f'version: "{version}"')
                return {"status": "complete", "summary": "Invalid selection", "evidence": plan["evidence"],
                        "missing_information": [], "path": "requirement.md", "content": text}
            assert "strategy_group" in payload["validation_error"] or "strategy_capability" in payload["validation_error"]
            assert (source.directory / "Dockerfile").is_file()

    client = Client(plan, callback=bad_first)
    assert build(source, plan, client=client).status == "generated"
    assert calls == 2
    assert [r.get("target_path") for r in client.requests].count("agent.toml") == 1


def test_valid_nondefault_id_and_exact_string_version_are_preserved(source, plan):
    requirement = REQUIREMENT.replace("TEST-GENERAL", "TEST-RESEARCH").replace('version: "1"', 'version: "7"')
    assert build(source, plan, client=Client(plan, files={**FILES, "requirement.md": requirement})).status == "generated"
    assert (source.directory / "requirement.md").read_text() == requirement


def test_missing_selection_is_not_silently_accepted_as_default(source, plan):
    absent = REQUIREMENT.replace(
        'strategy_group:\n  schema_version: kuma.strategy_group_selection.v1\n  id: TEST-GENERAL\n  version: "1"\n', "")
    with pytest.raises(BuildError, match="must declare strategy_group"):
        build(source, plan, client=Client(plan, files={**FILES, "requirement.md": absent}))
    assert not (source.directory / "requirement.md").exists()


def test_changed_catalog_replans_and_reports_obsolete_existing_selection(source, plan, monkeypatch):
    build(source, plan)
    updated = context()
    catalog = updated["strategy_group_catalog"]
    catalog["catalog_release"] = "b" * 64
    catalog["default"]["version"] = "2"
    catalog["groups"][0]["version"] = "2"
    monkeypatch.setattr(onboarding_catalog, "fetch", lambda **kwargs: updated)
    client = Client(plan)
    result = build(source, plan, client=client)
    assert result.status == "conflict" and "requirement.md" in result.messages[0]
    assert [request.get("target_path") for request in client.requests] == [None]
    assert (source.directory / "requirement.md").read_text() == REQUIREMENT


def test_catalog_credentials_are_not_written_or_sent(source, plan, monkeypatch):
    secret = "private-catalog-credential-12345678"
    snapshot = context()
    snapshot["strategy_group_catalog"]["groups"][0]["description"] = secret
    monkeypatch.setattr(onboarding_catalog, "fetch", lambda **kwargs: snapshot)
    client = Client(plan)
    with pytest.raises(BuildError, match="contains credentials"):
        build(source, plan, client=client, environ={"KUMA_API_KEY": secret})
    assert client.requests == []
    records = records_directory(source.directory, source.directory.parents[1] / "registry.toml")
    assert not any(secret in path.read_text() for path in records.rglob("*.json"))
