from agentbench.cli.main import cli
from agentbench.observe.catalog import select_agent
import pytest
import os
import json
import subprocess
import sys
from pathlib import Path


def test_menu_includes_enabled_adapting_company(capsys):
    assert cli(["observe", "--list"]) == 0
    output = capsys.readouterr().out
    assert "1. company-research-agent" in output
    assert "adapting" in output


def test_quit_without_credentials(monkeypatch):
    monkeypatch.setattr("builtins.input", lambda _: "q")
    assert cli(["observe"]) == 0


@pytest.mark.parametrize("selection", [["1"], ["company-research-agent"], ["--agent", "1"]])
def test_direct_selection_skips_menu_and_selection_prompt(monkeypatch, capsys, selection):
    from agentbench.cli.features import observe as feature
    calls = []
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Must not ask for Agent selection again"))
    monkeypatch.setattr(feature, "native_input", lambda agent, path: {"company": "Test"})
    monkeypatch.setattr(feature, "load_project_environment", lambda path: None)
    monkeypatch.setattr(feature, "observe", lambda agent, value, **kwargs: calls.append((agent, value, kwargs)))
    assert cli(["observe", *selection, "--model", "provider/test-model"]) == 0
    assert len(calls) == 1
    assert calls[0][0].agent_id == "company-research-agent"
    assert calls[0][1] == {"company": "Test"}
    assert calls[0][2]["environ"]["OPENROUTER_MODEL"] == "provider/test-model"
    output = capsys.readouterr().out
    assert "Enabled Agents:" not in output
    assert "Selected Agent: company-research-agent" in output


def test_invalid_direct_selection_does_not_fall_back_to_menu(monkeypatch, capsys):
    monkeypatch.setattr("builtins.input", lambda _: pytest.fail("Invalid explicit selection must fail"))
    assert cli(["observe", "999"]) == 1
    assert "Enabled Agents:" not in capsys.readouterr().out


@pytest.mark.parametrize("arguments", [["1", "--agent", "1"], ["--model", "1"], ["--model"]])
def test_ambiguous_or_incomplete_arguments_fail_before_menu(arguments, capsys):
    with pytest.raises(SystemExit) as exc:
        cli(["observe", *arguments])
    assert exc.value.code == 2
    output = capsys.readouterr()
    assert "Enabled Agents:" not in output.out
    if arguments == ["--model", "1"]:
        assert "observe 1" in output.err


def test_selection_boundaries():
    records = [{"agent_id": "one"}, {"agent_id": "two"}]
    assert select_agent(records, "2")["agent_id"] == "two"
    assert select_agent(records, "one")["agent_id"] == "one"
    for choice in ("0", "-1", "3", "disabled"):
        with pytest.raises(ValueError):
            select_agent(records, choice)


def test_module_cli_entry_from_checkout():
    repo = Path(__file__).resolve().parents[2]
    result = subprocess.run([sys.executable, "-m", "agentbench", "observe", "--list"], cwd=repo,
                            capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stderr
    assert "1. company-research-agent" in result.stdout


@pytest.mark.skipif(os.getenv("ABB_DOCKER_TEST") != "1", reason="Opt-in CLI → real Docker integration")
def test_interactive_selection_to_real_docker_trace(offline_agent, tmp_path, monkeypatch, capsys):
    resources = tmp_path / "resources"
    resources.mkdir()
    registry = resources / "registry.toml"
    registry.write_text('''schema_version = "defuzex-bench.registry.v1"
[[agents]]
agent_id = "offline-observe"
path = "unit"
enabled = true
status = "adapting"
framework = "langgraph"
''')
    (offline_agent.path / "requirement.md").write_text("Offline arithmetic graph")
    request = tmp_path / "input.json"
    request.write_text(json.dumps({"number": 5, "text": "CLI中文"}))
    monkeypatch.setattr("builtins.input", lambda _: "1")
    output = tmp_path / "runs"
    assert cli(["observe", "--registry", str(registry), "--input", str(request), "--output", str(output)]) == 0
    directories = list(output.iterdir())
    assert len(directories) == 1
    saved = json.loads((directories[0] / "run.json").read_text())
    assert saved["status"] == "succeeded" and saved["output"] == "CLI中文:13"
    assert saved["trace_summary"]["framework:span_start"] >= 3
    assert cli(["observe", "--show", str(directories[0])]) == 0
    assert "double [ok]" in capsys.readouterr().out
