"""Exercise the public SDK seam through a real local Agent invocation."""

import builtins
from types import SimpleNamespace

import pytest

from agentbench.harness import BenchmarkRunner, ProviderSelectionError, SuiteRunner
from tests.test_benchmark_runner import FakeSDKRun


def forbid_defuzex(monkeypatch):
    original = builtins.__import__

    def guarded(name, *args, **kwargs):
        if name == "defuzex" or name.startswith("defuzex."):
            raise AssertionError("A custom SDK must not import DefuzeX")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded)


def test_sdk_module_receives_only_its_own_options(starter_agent, monkeypatch):
    forbid_defuzex(monkeypatch)
    calls = []

    def create_run(*, repo_path, difficulty):
        calls.append((repo_path, difficulty))
        return FakeSDKRun()

    options = {"difficulty": "bounded"}
    runner = BenchmarkRunner(
        sdk=SimpleNamespace(create_run=create_run), sdk_options=options, environ={}
    )
    result = runner.run(starter_agent)

    assert result.passed
    assert calls == [(starter_agent.path, "bounded")]
    assert options == {"difficulty": "bounded"}


def test_sdk_suite_creates_a_fresh_run_for_each_case(starter_agent, monkeypatch):
    from dataclasses import replace

    forbid_defuzex(monkeypatch)
    runs = []

    def create_run(*, repo_path):
        assert repo_path == starter_agent.path
        run = FakeSDKRun()
        runs.append(run)
        return run

    result = SuiteRunner(sdk=SimpleNamespace(create_run=create_run)).run(
        [replace(starter_agent, case_count=2)]
    )
    assert result.passed
    assert result.items[0].completed_case_count == 2
    assert len(runs) == 2
    assert runs[0] is not runs[1]


def test_bad_sdk_is_rejected_before_starting_agent(starter_agent):
    class NoAgent:
        def start(self, registration):
            pytest.fail("Invalid SDK must be rejected before Agent startup")

    with pytest.raises(ProviderSelectionError, match="create_run"):
        BenchmarkRunner(sdk=object(), agent_runner=NoAgent()).run(starter_agent)


def test_sdk_and_legacy_factory_cannot_silently_override_each_other():
    with pytest.raises(ValueError, match="sdk_run_factory"):
        BenchmarkRunner(sdk=object(), sdk_run_factory=lambda **kw: FakeSDKRun())


def test_injected_sdk_failure_keeps_step_callback(starter_agent):
    from tests.test_benchmark_runner import FailingSubmitSDKRun

    failures = []
    runner = BenchmarkRunner(
        sdk=SimpleNamespace(create_run=lambda **kw: FailingSubmitSDKRun())
    )
    with pytest.raises(RuntimeError, match="judge unavailable"):
        runner.run(
            starter_agent,
            on_step_failure=lambda agent_id, failure: failures.append(failure),
        )
    assert failures[0].output == "DEFUZEX_AGENT_READY"


def test_offline_example_sdk_executes_real_langgraph(starter_agent, monkeypatch):
    from examples import local_sdk

    forbid_defuzex(monkeypatch)
    result = BenchmarkRunner(sdk=local_sdk).run(starter_agent)
    assert result.passed
    assert result.report.confidence == 1.0
    assert result.history_count == 1


def test_cli_python_entry_passes_sdk_to_real_execution(starter_agent, monkeypatch):
    from dataclasses import replace

    from agentbench.cli.features.run import run
    from agentbench.harness import AgentRegistry
    from examples import local_sdk

    forbid_defuzex(monkeypatch)
    monkeypatch.setattr(
        "agentbench.cli.features.run.load_registry",
        lambda path: AgentRegistry([replace(starter_agent, enabled=True)]),
    )
    code = run(
        sdk=local_sdk,
        input_fn=lambda _: "y",
        output_fn=lambda _: None,
        sleep_fn=lambda _: None,
    )
    assert code == 0


def test_cli_module_selection_and_options_reach_run(monkeypatch, tmp_path):
    import json

    from agentbench.cli.main import cli
    from examples import local_sdk

    options = tmp_path / "sdk-options.json"
    options.write_text(json.dumps({"expected": "hello"}), encoding="utf-8")
    received = []
    monkeypatch.setattr(
        "agentbench.cli.features.run.run",
        lambda **kw: received.append(kw) or 0,
    )
    assert (
        cli(["run", "--sdk", "examples.local_sdk", "--sdk-options", str(options)]) == 0
    )
    assert received[0]["sdk_selection"].value is local_sdk
    assert received[0]["sdk_selection"].reference.source == "python"
    assert received[0]["sdk_options"] == {"expected": "hello"}


def test_cli_rejects_invalid_options_without_echoing_contents(tmp_path, capsys):
    from agentbench.cli.main import cli

    options = tmp_path / "sdk-options.json"
    options.write_text('{"secret": "private-test-value",', encoding="utf-8")
    assert cli(["run", "--sdk-options", str(options)]) == 2
    assert "private-test-value" not in capsys.readouterr().out


@pytest.mark.parametrize("judge", [False, True])
def test_real_defuzex_module_uses_public_run_contract(tmp_path, judge):
    """Optional local SDK integration: real StateGraph and real DefuzeX Run."""
    from uuid import uuid4

    from agentbench.harness import AgentRegistration

    defuzex = pytest.importorskip("defuzex")
    module = f"sdk_contract_graph_{uuid4().hex}"
    source = tmp_path / "agent"
    source.mkdir()
    (source / f"{module}.py").write_text(
        "from typing import TypedDict\n"
        "from langgraph.graph import StateGraph, START, END\n"
        "class State(TypedDict):\n    prompt: str\n    response: str\n"
        "builder = StateGraph(State)\n"
        'builder.add_node("echo", lambda state: {"response": state["prompt"]})\n'
        'builder.add_edge(START, "echo")\n'
        'builder.add_edge("echo", END)\n'
        "graph = builder.compile()\n",
        encoding="utf-8",
    )
    (source / "langgraph.json").write_text(
        '{"graphs": {"agent": "' + module + '.py:graph"}}',
        encoding="utf-8",
    )
    (tmp_path / "agent.toml").write_text(
        '[adapter]\ntype="langgraph"\nconfig="langgraph.json"\n'
        'graph_id="agent"\ninput_key="prompt"\noutput_key="response"\n',
        encoding="utf-8",
    )

    class Cases:
        requirement_required = False

        def generate_case(self, context):
            return {
                "inputs": ["SDK seam works"],
                "rubric": {"criteria": ["Echo the input"]},
            }

    def evaluate(context):
        assert context.history[0].submission.output == "SDK seam works"
        return {"status": "pass", "confidence": 1.0}

    agent = AgentRegistration(
        "sdk-contract", tmp_path, True, "ready", "langgraph", "local"
    )
    result = BenchmarkRunner(
        sdk=defuzex,
        sdk_options={
            "case_provider": Cases(),
            "max_inputs": 1,
            "judge": judge,
            "judge_provider": evaluate if judge else None,
            "allow_local": True,
            "track_files": False,
        },
    ).run(agent)
    assert result.run_state == ("report_ready" if judge else "completed")
    assert result.passed is judge
    assert result.history_count == 1
    assert result.steps[0].invocation.output == "SDK seam works"
