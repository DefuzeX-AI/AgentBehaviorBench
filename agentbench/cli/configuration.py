"""Configuration objects for AgentBench CLI operations."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path

from agentbench.cli.viewer import RunningViewer, start_viewer_server
from agentbench.harness import SDK, SuiteRunner
from agentbench.runtime.interception import DEFAULT_TRACE_MAX_BYTES
from agentbench.sdk.plugins import SDKSelection


@dataclass(frozen=True)
class RunConfiguration:
    """Dependencies and options for one benchmark run."""

    input_fn: Callable[[str], str] = input
    output_fn: Callable[[str], None] = print
    suite_runner: SuiteRunner | None = None
    sdk: SDK | None = None
    sdk_selection: SDKSelection | None = None
    sdk_options: Mapping[str, object] | None = None
    output_path: str | Path | None = None
    viewer_starter: Callable[[Path], RunningViewer] | None = start_viewer_server
    post_run_input_fn: Callable[[str], str] = input
    llm_trace_max_bytes: int = DEFAULT_TRACE_MAX_BYTES
    model: str | None = None
