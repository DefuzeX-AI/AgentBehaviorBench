import importlib
import json

import pytest
from dataclasses import dataclass

from agentbench.cli.constants import (
    AGENT_REVEAL_DELAY_SECONDS,
    ANSI_GREEN,
    ANSI_RED,
    ANSI_RESET,
    LOGO_PAUSE_SECONDS,
)
from agentbench.cli.logo import BBA_LOGO
from agentbench.cli.main import (
    cli,
    confirm_agents,
    main,
)
from agentbench.harness import (
    AgentRegistration,
    BenchmarkProgress,
    BenchmarkSuiteResult,
    ProviderSelectionError,
    SuiteAgentResult,
)
from tests.support.results import benchmark_result


@pytest.fixture(autouse=True)
def isolated_cli_registry(monkeypatch, ready_agents):
    from agentbench.harness import AgentRegistry
    monkeypatch.setattr(
        "agentbench.cli.features.run.load_registry",
        lambda path: AgentRegistry(list(ready_agents)),
    )


@dataclass(frozen=True)
class FakeViewer:
    url: str = "http://127.0.0.1:8765"


class FakeSuiteRunner:
    def __init__(
        self,
        *,
        error: Exception | None = None,
        result_status: str = "pass",
    ) -> None:
        self.error = error
        self.result_status = result_status
        self.calls: list[tuple[object, dict[str, object]]] = []
        self.suite_count = 0

    def new_suite_id(self) -> str:
        self.suite_count += 1
        return f"suite_test_{self.suite_count}"

    def run(self, agents, **kwargs):  # type: ignore[no-untyped-def]
        selected = tuple(agents)
        self.calls.append((selected, kwargs))
        if self.error is not None:
            raise self.error

        progress = kwargs.get("on_progress")
        if callable(progress):
            progress(BenchmarkProgress("sdk_check", "started"))
            progress(
                BenchmarkProgress(
                    "sdk_check", "succeeded", detail="Provider mode: official"
                )
            )

        items = []
        for index, agent in enumerate(selected, start=1):
            start = kwargs.get("on_agent_start")
            if callable(start):
                start(agent, index, len(selected))
            if callable(progress):
                progress(BenchmarkProgress("agent_start", "started", agent.agent_id))
                progress(
                    BenchmarkProgress(
                        "agent_start",
                        "succeeded",
                        agent.agent_id,
                        "FakeAdapter",
                    )
                )
            benchmark = benchmark_result(
                agent.agent_id,
                status=self.result_status,
                with_step=True,
            )
            step_start = kwargs.get("on_step_start")
            if callable(step_start):
                step_start(
                    agent.agent_id,
                    benchmark.steps[0].input_id,
                    benchmark.steps[0].payload,
                )
            step_complete = kwargs.get("on_step_complete")
            if callable(step_complete):
                step_complete(agent.agent_id, benchmark.steps[0])
            item = SuiteAgentResult(
                agent_id=agent.agent_id,
                benchmarks=tuple(benchmark for _ in range(agent.case_count)),
                requested_case_count=agent.case_count,
            )
            items.append(item)
            complete = kwargs.get("on_agent_complete")
            if callable(complete):
                complete(item)
        return BenchmarkSuiteResult(
            suite_id=str(kwargs["suite_id"]),
            selected_agent_ids=tuple(agent.agent_id for agent in selected),
            items=tuple(items),
        )


def test_cli_detects_agent_and_accepts_yes(
    ready_agents: tuple[AgentRegistration, ...],
) -> None:
    """Check CLI prints agents and accepts yes."""
    output: list[str] = []
    delays: list[float] = []
    prompts: list[str] = []
    runner = FakeSuiteRunner()

    exit_code = main(
        input_fn=lambda prompt: prompts.append(prompt) or "y",
        output_fn=output.append,
        suite_runner=runner,  # type: ignore[arg-type]
        sleep_fn=delays.append,
    )

    assert exit_code == 0
    assert len(runner.calls) == 1
    assert prompts == ["Continue? [yes/no]: "]
    assert output[0] == BBA_LOGO
    for agent in ready_agents:
        assert any(agent.agent_id in line for line in output)
        assert any(f"cases: {agent.case_count}" in line for line in output)
    assert any(
        f"Running: [1/{len(ready_agents)}] {ready_agents[0].agent_id}" in line
        for line in output
    )
    assert any(f"{ANSI_GREEN}OK{ANSI_RESET}" in line for line in output)
    assert output[-1] == (
        f"\nSuite complete: {len(ready_agents)} passed, 0 failed, 0 skipped, "
        f"{len(ready_agents)} selected."
    )
    selected, kwargs = runner.calls[0]
    assert selected == ready_agents
    assert "allow_local" not in kwargs
    assert "track_files" not in kwargs
    assert delays == [
        LOGO_PAUSE_SECONDS,
        *([AGENT_REVEAL_DELAY_SECONDS] * (len(ready_agents) + 1)),
    ]


def test_cli_can_decline() -> None:
    """Check CLI accepts no."""
    output: list[str] = []
    runner = FakeSuiteRunner()

    exit_code = main(
        input_fn=lambda _: "n",
        output_fn=output.append,
        suite_runner=runner,  # type: ignore[arg-type]
        sleep_fn=lambda _: None,
    )

    assert exit_code == 0
    assert output[-1] == "Cancelled."
    assert runner.calls == []


def test_confirmation_result_can_gate_execution(
    enabled_agents: tuple[AgentRegistration, ...],
) -> None:
    assert confirm_agents(
        enabled_agents,
        input_fn=lambda _: "yes",
        output_fn=lambda _: None,
        sleep_fn=lambda _: None,
    )
    assert not confirm_agents(
        enabled_agents,
        input_fn=lambda _: "no",
        output_fn=lambda _: None,
        sleep_fn=lambda _: None,
    )


def test_cli_reports_provider_configuration_error() -> None:
    output: list[str] = []
    runner = FakeSuiteRunner(error=ProviderSelectionError("DEFUZEX_API_KEY is missing"))

    exit_code = main(
        input_fn=lambda _: "yes",
        output_fn=output.append,
        suite_runner=runner,  # type: ignore[arg-type]
        sleep_fn=lambda _: None,
    )

    assert exit_code == 1
    assert output[-1] == (
        f"{ANSI_RED}【Configuration error】 DEFUZEX_API_KEY is missing{ANSI_RESET}"
    )


def test_main_writes_json_result_snapshot(
    tmp_path, enabled_agents: tuple[AgentRegistration, ...]
) -> None:
    output: list[str] = []
    runner = FakeSuiteRunner()
    output_path = tmp_path / "result.json"
    post_run_answers = iter(["r", "q"])

    def start_locked_viewer(path):  # type: ignore[no-untyped-def]
        first_event = json.loads(path.read_text(encoding="utf-8"))[0]
        return FakeViewer(
            url=(f"http://127.0.0.1:8765/suite/{first_event['suite_id']}/")
        )

    exit_code = main(
        input_fn=lambda _: "yes",
        output_fn=output.append,
        suite_runner=runner,  # type: ignore[arg-type]
        sleep_fn=lambda _: None,
        output_path=output_path,
        viewer_starter=start_locked_viewer,  # type: ignore[arg-type]
        post_run_input_fn=lambda _: next(post_run_answers),
    )

    artifacts = sorted(tmp_path.glob("result-*.json"))
    assert len(artifacts) == 2
    lines = json.loads(artifacts[0].read_text(encoding="utf-8"))
    assert exit_code == 0
    assert f"Result artifact started: {artifacts[0]}" in output
    assert any(
        line.startswith("View: http://127.0.0.1:8765/suite/suite_test_")
        for line in output
    )
    assert any(
        line.startswith("View: http://127.0.0.1:8765/suite/suite_test_")
        and "#agent=" in line
        and "//#agent=" not in line
        for line in output
    )
    assert any(f"Result saved: {artifacts[0]}" in line for line in output)
    assert any(
        f"Open later: python -m agentbench view {artifacts[0]}" in line
        for line in output
    )
    assert "Viewer stopped. Rerunning benchmark." in output
    assert "Viewer stopped." in output
    assert lines[0]["event"] == "run_started"
    assert lines[-1]["event"] == "suite_completed"
    suite_ids = []
    for artifact in artifacts:
        events = json.loads(artifact.read_text(encoding="utf-8"))
        assert {event["suite_id"] for event in events} == {events[0]["suite_id"]}
        suite_ids.append(events[0]["suite_id"])
    assert set(suite_ids) == {"suite_test_1", "suite_test_2"}
    assert any(event["event"] == "step_started" for event in lines)
    assert any(event["event"] == "step_completed" for event in lines)
    assert lines[-1]["summary"]["suite_passed"] is True


def test_cli_parses_output_argument(monkeypatch, tmp_path) -> None:
    calls: list[dict[str, object]] = []
    output_path = tmp_path / "result.json"

    def fake_run(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return 7

    monkeypatch.setattr("agentbench.cli.features.run.run", fake_run)

    assert cli(["--output", str(output_path)]) == 7
    assert calls == [{"output_path": str(output_path)}]

    assert cli(["run", "--output", str(output_path)]) == 7
    assert calls[-1] == {"output_path": str(output_path)}


def test_cli_parses_terminal_llm_trace_options(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(**kwargs):  # type: ignore[no-untyped-def]
        calls.append(kwargs)
        return 0

    monkeypatch.setattr("agentbench.cli.features.run.run", fake_run)

    assert (
        cli(
            [
                "run",
                "--model",
                "openai/gpt-4.1-mini",
                "--llm-trace",
                "terminal",
                "--llm-trace-max-bytes",
                "4096",
            ]
        )
        == 0
    )
    assert calls == [
        {
            "output_path": "results/result.json",
            "model": "openai/gpt-4.1-mini",
            "llm_trace": "terminal",
            "llm_trace_max_bytes": 4096,
        }
    ]


def test_cli_dispatches_view_command(monkeypatch, tmp_path) -> None:
    calls: list[tuple[str, str, int]] = []
    result_log = tmp_path / "result.json"

    def fake_serve(path, *, host, port):  # type: ignore[no-untyped-def]
        calls.append((str(path), host, port))

    monkeypatch.setattr("agentbench.cli.features.view.serve_result_log", fake_serve)

    assert cli(["view", str(result_log), "--port", "9000"]) == 0
    assert calls == [(str(result_log), "127.0.0.1", 9000)]


def test_legacy_console_entry_dispatches_cli_args(monkeypatch, tmp_path) -> None:
    calls: list[list[str]] = []
    output_path = tmp_path / "result.json"

    def fake_cli(argv):  # type: ignore[no-untyped-def]
        calls.append(list(argv))
        return 5

    cli_main_module = importlib.import_module("agentbench.cli.main")
    monkeypatch.setattr(cli_main_module, "cli", fake_cli)
    monkeypatch.setattr("sys.argv", ["agentbench", "--output", str(output_path)])

    assert main() == 5
    assert calls == [["--output", str(output_path)]]
