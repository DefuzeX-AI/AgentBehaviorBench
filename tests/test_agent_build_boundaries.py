"""Source privacy, output boundaries and exact CLI stage selection."""
import json
from dataclasses import replace
import pytest
from agentbench.cli.main import cli
from agentbench.harness.registry import load_registry
from agentbench.onboarding.build_agent_env.common.errors import BuildError
from agentbench.onboarding.build_agent_env.common.records import records_directory
from agentbench.onboarding.build_agent_env.openrouter_provider.context import collect_context
from agentbench.onboarding.build_agent_env.openrouter_provider.settings import load_settings
from agentbench.onboarding.discovery import discover_files
from agentbench.onboarding.resume import download_or_reuse
from tests.agent_build_fixtures import source, plan, Client, build, write, URL, FILES, REQUIREMENT


def test_context_follows_imports_but_excludes_secrets_and_symlinks(source, tmp_path):
    secret = "known-secret-value-1234567"
    write(source.directory, "agent/.env", f"TOKEN={secret}")
    write(source.directory, "agent/.env.example", f"TAVILY_API_KEY={secret}")
    write(source.directory, "agent/README.md", f"Credential: {secret}")
    outside = write(tmp_path, "outside.py", "PRIVATE_HOST_CONTENT")
    (source.directory / "agent/linked.py").symlink_to(outside)
    source = replace(source, files=(*discover_files(source.directory / "agent"), ".env", "linked.py"))
    context = collect_context(source, load_settings(), {"TOKEN": secret})
    names = {item["path"] for item in context["files"]}
    assert {"src/pkg/graph.py", "src/pkg/state.py", "src/pkg/tools.py"} <= names
    assert ".env" not in names and "linked.py" not in names
    assert secret not in json.dumps(context) and "PRIVATE_HOST_CONTENT" not in json.dumps(context)
    assert "TAVILY_API_KEY" in json.dumps(context)


def test_context_budget_is_enforced_after_redaction(source):
    write(source.directory, "agent/.env.example", "A=1\nB=2\nC=3")
    source = replace(source, files=(".env.example",))
    settings = replace(load_settings(), max_context_bytes=16, max_file_bytes=16)
    context = collect_context(source, settings, {})
    assert context["content_bytes"] <= 16 and context["files"][0]["truncated"]


@pytest.mark.parametrize("name", ["../.env", "/tmp/stolen", "agent/graph.py", "registry.toml", "evaluation/input-contract.json"])
def test_wrong_target_in_model_response_is_rejected(source, plan, name):
    def wrong(payload):
        if "target_path" in payload:
            return {"status": "complete", "summary": "Wrong target", "evidence": plan["evidence"],
                    "missing_information": [], "path": name, "content": "bad"}
    with pytest.raises(BuildError, match="response schema"):
        build(source, plan, client=Client(plan, callback=wrong))
    assert not (source.directory / "agent.toml").exists()


def test_multi_file_response_is_no_longer_accepted(source, plan):
    def bundle(payload):
        if "target_path" in payload:
            return {**plan, "files": [{"path": name, "content": text} for name, text in FILES.items()]}
    with pytest.raises(BuildError, match="response schema"):
        build(source, plan, client=Client(plan, callback=bundle))
    assert not (source.directory / "agent.toml").exists()


def test_secret_response_is_not_recorded_or_retried(source, plan):
    secret = "private-key-123456789"
    plan["summary"] = secret
    client = Client(plan)
    with pytest.raises(BuildError, match="credential"):
        build(source, plan, client=client, environ={"API_KEY": secret})
    assert len(client.requests) == 1
    records = records_directory(source.directory, source.directory.parents[1] / "registry.toml")
    assert not any(secret in path.read_text() for path in records.rglob("*.json"))


def test_requirement_cannot_read_a_host_schema(source, plan, tmp_path):
    outside = write(tmp_path, "private-schema.json", '{"type":"object"}')
    requirement = REQUIREMENT.replace("input_type: text", f"input_type: structured\ninput_schema: {outside}")
    with pytest.raises(BuildError, match="relative local file"):
        build(source, plan, client=Client(plan, files={**FILES, "requirement.md": requirement}))
    assert not (source.directory / "requirement.md").exists()


def test_existing_source_is_reused_without_cloning(source, monkeypatch):
    monkeypatch.setattr("agentbench.onboarding.resume.download_agent", lambda *args: pytest.fail("unexpected clone"))
    assert download_or_reuse(URL + ".git", source.directory.parent).directory == source.directory


@pytest.mark.parametrize("flags,expected", [([], []), (["-b"], ["build"]), (["-c"], ["certify"]), (["-b", "-c"], ["build", "certify"])])
def test_cli_stage_combinations(source, plan, monkeypatch, flags, expected):
    from agentbench.onboarding import workflow
    from agentbench.cli.features import certify as feature
    calls = []
    if flags == ["-c"]:
        for name, content in FILES.items():
            write(source.directory, name, content)
    monkeypatch.setattr("agentbench.cli.features.agent.download_agent", lambda *args: source)
    monkeypatch.setattr(workflow, "load_project_environment", lambda *args: None)
    monkeypatch.setattr(workflow, "build_agent_environment", lambda *args, **kwargs: calls.append("build") or build(source, plan))
    def certify(agent_id, **kwargs):
        assert load_registry(kwargs["registry_path"]).find(agent_id).status == "adapting"
        calls.append("certify")
        return 0
    monkeypatch.setattr(feature, "certify", certify)
    registry = source.directory.parents[1] / "registry.toml"
    assert cli(["agent", "add", URL, "--agents-dir", str(source.directory.parent), "--registry", str(registry), *flags]) == 0
    assert calls == expected


def test_certify_without_configuration_never_requests_ai(source, monkeypatch, capsys):
    from agentbench.onboarding import workflow
    monkeypatch.setattr(workflow, "load_project_environment", lambda *args: None)
    monkeypatch.setattr(workflow, "build_agent_environment", lambda *args, **kwargs: pytest.fail("unexpected model call"))
    assert cli(["agent", "add", URL, "--agents-dir", str(source.directory.parent), "-c"]) == 2
    assert "Missing or unsafe integration file" in capsys.readouterr().err


def test_real_cli_dispatch_saves_files_and_resumes_the_failed_stage(source, plan, monkeypatch, capsys):
    from agentbench.onboarding import workflow
    from agentbench.onboarding.build_agent_env import service
    from agentbench.runtime.agentcontainer.config import tomllib
    broken = {**FILES, "Dockerfile": "FROM python:3.11\nUSER root\n"}
    client = Client(plan, files=broken)
    monkeypatch.setattr(workflow, "load_project_environment", lambda *args: None)
    monkeypatch.setattr(service, "OpenRouterClient", lambda *args, **kwargs: client)
    registry = source.directory.parents[1] / "registry.toml"
    command = ["agent", "add", URL, "-b", "--agents-dir", str(source.directory.parent), "--registry", str(registry)]
    assert cli(command) == 2
    assert "agent.toml: saved" in capsys.readouterr().err
    assert (source.directory / "agent.toml").is_file() and not registry.exists()
    client = Client(plan)
    assert cli(command) == 0
    output = capsys.readouterr().err
    assert "Plan: reused" in output and "agent.toml: reused" in output
    assert "Dockerfile: saved" in output
    assert [request.get("target_path") for request in client.requests] == ["Dockerfile", "requirement.md"]
    assert tomllib.loads(registry.read_text())["agents"][0]["status"] == "adapting"


def test_unit_lock_blocks_a_second_builder_before_any_model_request(source, plan):
    from agentbench.harness.session.locking import SuiteLock, SuiteLockedError
    lock = SuiteLock(records_directory(source.directory, source.directory.parents[1] / "registry.toml"))
    lock.acquire()
    client = Client(plan)
    try:
        with pytest.raises(SuiteLockedError):
            build(source, plan, client=client)
    finally:
        lock.close()
    assert client.requests == []


def test_changed_source_invalidates_plan_but_preserves_valid_files(source, plan):
    build(source, plan)
    write(source.directory, "agent/README.md", "Updated source documentation")
    client = Client(plan)
    assert build(source, plan, client=client).status == "generated"
    assert [request.get("target_path") for request in client.requests] == [None]


def test_context_includes_application_lifecycle_before_translated_readmes(source):
    write(source.directory, "agent/application.py", "from pkg.graph import graph\ndef run_job(value):\n return graph.invoke(value)\n")
    write(source.directory, "agent/README.es.md", "x" * 1000)
    discovered = discover_files(source.directory / "agent")
    assert "application.py" in discovered
    current = replace(source, files=discovered)
    settings = replace(load_settings(), max_context_bytes=1000)
    context = collect_context(current, settings, {})
    names = [entry["path"] for entry in context["files"]]
    assert "application.py" in names
    assert names.index("application.py") < names.index("README.es.md")
