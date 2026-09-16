"""Terminal presentation shared by AgentBench CLI features."""

from __future__ import annotations

import re
import time
from collections.abc import Callable
from pathlib import Path
from urllib.parse import quote

from agentbench.harness import SuiteAgentResult
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.result import BenchmarkSuiteResult

from .constants import (
    AGENT_REVEAL_DELAY_SECONDS,
    AGENT_SEPARATOR_WIDTH,
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_GREEN,
    ANSI_MAGENTA,
    ANSI_RED,
    ANSI_RESET,
    ANSI_YELLOW,
)

PANEL_WIDTH = AGENT_SEPARATOR_WIDTH
PANEL_INNER_WIDTH = PANEL_WIDTH - 2
ANSI_PATTERN = re.compile(r"\033\[[0-9;]*m")


def confirm_agents(
    agents: tuple[AgentRegistration, ...],
    *,
    input_fn: Callable[[str], str] = input,
    output_fn: Callable[[str], None] = print,
) -> bool:
    """Print detected agents and return whether execution was confirmed."""

    print_agents(
        agents,
        output_fn,
    )
    try:
        confirmed = request_confirmation(input_fn, output_fn)
    except (EOFError, KeyboardInterrupt, OSError, RuntimeError):
        output_fn("\nCancelled.")
        return False

    if not confirmed:
        output_fn("Cancelled.")
        return False

    output_fn("")
    output_fn(panel_rule("RUN QUEUED", ANSI_GREEN))
    output_fn(
        panel_line(
            f"{ANSI_GREEN}OK{ANSI_RESET}  {len(agents)} benchmark agent(s) selected"
        )
    )
    output_fn(panel_line("Next stage: evaluation SDK configuration check"))
    output_fn(panel_rule("", ANSI_GREEN))
    return True


def print_agents(
    agents: tuple[AgentRegistration, ...],
    output_fn: Callable[[str], None],
) -> None:
    """Print the detected agent list."""

    output_fn("")
    output_fn(panel_rule("AGENT DISCOVERY", ANSI_CYAN))
    output_fn(
        panel_line(
            f"{ANSI_BOLD}Detected benchmark agents:{ANSI_RESET} "
            f"{len(agents)} ready for selection"
        )
    )
    output_fn(panel_line(""))
    for index, agent in enumerate(agents, start=1):
        time.sleep(AGENT_REVEAL_DELAY_SECONDS)
        marker = f"{ANSI_MAGENTA}{index:02d}{ANSI_RESET}"
        status = (
            f"{ANSI_GREEN}{agent.status.upper()}{ANSI_RESET}"
            if agent.status == "ready"
            else agent.status.upper()
        )
        output_fn(panel_line(f"{marker}  {agent.agent_id}"))
        output_fn(
            panel_line(
                f"    framework: {ANSI_BLUE}{agent.framework}{ANSI_RESET}"
                f"    status: {status}    cases: {agent.case_count}"
            )
        )
        output_fn(panel_line(f"    path: {display_path(agent.path)}"))
        if index < len(agents):
            output_fn(panel_line("    " + "." * 64))
    if agents:
        time.sleep(AGENT_REVEAL_DELAY_SECONDS)
    output_fn(panel_rule("", ANSI_CYAN))


def request_confirmation(
    input_fn: Callable[[str], str], output_fn: Callable[[str], None]
) -> bool:
    while True:
        answer = input_fn("Continue? [yes/no]: ").strip().lower()
        if answer in {"confirm", "c", "yes", "y"}:
            return True
        if answer in {"cancel", "n", "no", ""}:
            return False
        output_fn("Enter 'yes' or 'no'.")


def print_agent_start(
    agent: AgentRegistration,
    index: int,
    total: int,
    output_fn: Callable[[str], None],
) -> None:
    output_fn("\n" + "-" * AGENT_SEPARATOR_WIDTH)
    output_fn(f"Running: [{index}/{total}] {agent.agent_id}")


def print_agent_complete(
    item: SuiteAgentResult, output_fn: Callable[[str], None]
) -> None:
    for case in item.case_results:
        artifacts = case.artifacts or {}
        report = artifacts.get('received_report')
        if report and not report.get('host_accepted'):
            output_fn(f"Judge retained | Case {case.case_index + 1}: {report['status']} | "
                      f"Host rejected | {artifacts.get('directory', '')}/{report['path']}")
    color = ANSI_GREEN if item.passed else ANSI_YELLOW if item.status in {"cancelled", "skipped"} else ANSI_RED
    status = f"{color}{'PASS' if item.passed else item.status.upper()}{ANSI_RESET}"
    if item.error_type is not None and item.completed_case_count == 0:
        output_fn(
            f"Result: {status} | "
            f"{item.error_type}: {item.error_message}"
        )
        return

    detail = (
        f"Result: {status} | "
        f"cases={item.completed_case_count}/{item.requested_case_count}"
    )
    if item.error_type is not None:
        detail += f" | error={item.error_type}: {item.error_message}"
    output_fn(detail)


def print_suite_summary(
    result: BenchmarkSuiteResult, output_fn: Callable[[str], None]
) -> None:
    from collections import Counter
    cases = [case for item in result.items for case in item.case_results]
    completed = sum(case.execution_status == 'completed' for case in cases)
    planned = sum(item.requested_case_count for item in result.items)
    verdicts = Counter(case.judge_status for case in cases if case.judge_status is not None)
    rejected = sum(case.judge_status is not None and not getattr(case, 'judge_accepted', True)
                   for case in cases)
    judge = ', '.join(f'{status}={count}' for status, count in sorted(verdicts.items())) or 'no report'
    if rejected:
        judge += f' ({rejected} host rejected)'
    output_fn(f"\nCase execution: {completed}/{planned} completed | Judge: {judge}")
    output_fn(
        "\nSuite complete: "
        f"{result.passed_count} passed, "
        f"{result.failed_count} failed, "
        f"{result.skipped_count} skipped, "
        f"{result.selected_count} selected."
    )


def case_event_status(event):
    """Describe execution and Judge separately while retaining legacy exit policy."""
    case = event.get('case_result')
    status = getattr(case, 'execution_status', None) or event.get('status', 'running')
    verdict = getattr(case, 'judge_status', None)
    if verdict is None:
        return status
    retained = '' if getattr(case, 'judge_accepted', True) else ' (host rejected)'
    return f'{status} | judge={verdict}{retained}'


def print_viewer_footer(
    result_log_path: Path,
    viewer_url: str | None,
    output_fn: Callable[[str], None],
) -> None:
    output_fn("")
    output_fn(panel_rule("RESULT VIEWER", ANSI_CYAN))
    output_fn(panel_line(f"Result saved: {result_log_path}"))
    if viewer_url is not None:
        output_fn(panel_line(f"Live viewer: {viewer_url}"))
    from ..viewer import require_viewer_assets, ViewerUnavailable
    try:
        require_viewer_assets()
    except ViewerUnavailable as exc:
        output_fn(panel_line(str(exc)))
    output_fn(panel_line(f"Open later: python -m agentbench view {result_log_path}"))
    output_fn(panel_rule("", ANSI_CYAN))


def request_viewer_action(
    result_log_path: Path,
    viewer_url: str,
    *,
    input_fn: Callable[[str], str],
    output_fn: Callable[[str], None],
) -> str:
    output_fn(f"Viewer is running at {viewer_url}. Result log: {result_log_path}")
    while True:
        try:
            answer = input_fn("Viewer action? [r rerun/q quit]: ").strip().lower()
        except (EOFError, KeyboardInterrupt, OSError, RuntimeError):
            output_fn("\nViewer stopped.")
            return "quit"
        if answer in {"q", "quit", "exit", ""}:
            output_fn("Viewer stopped.")
            return "quit"
        if answer in {"r", "rerun", "retry", "again"}:
            output_fn("Viewer stopped. Rerunning benchmark.")
            return "rerun"
        output_fn("Enter 'r' to rerun or 'q' to quit.")


def agent_view_url(viewer_url: str, agent_id: str) -> str:
    separator = "" if viewer_url.endswith("/") else "/"
    return f"{viewer_url}{separator}#agent={quote(agent_id, safe='')}"


def panel_rule(title: str, color: str) -> str:
    if not title:
        return f"{color}+{'-' * PANEL_INNER_WIDTH}+{ANSI_RESET}"

    label = f" {title} "
    right = PANEL_INNER_WIDTH - len(label)
    return f"{color}+{label}{'-' * right}+{ANSI_RESET}"


def panel_line(text: str) -> str:
    content = f" {text}"
    padding = max(PANEL_INNER_WIDTH - visible_width(content), 0)
    return f"{ANSI_CYAN}|{ANSI_RESET}{content}{' ' * padding}{ANSI_CYAN}|{ANSI_RESET}"


def display_path(path: Path) -> str:
    # presentation.py -> terminal_ui -> cli -> agentbench -> repository root
    repo_root = Path(__file__).resolve().parents[3]
    try:
        return str(path.relative_to(repo_root))
    except ValueError:
        return str(path)


def visible_width(text: str) -> int:
    return len(ANSI_PATTERN.sub("", text))
