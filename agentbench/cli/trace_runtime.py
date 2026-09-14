"""Build benchmark runners with model interception trace output."""

from __future__ import annotations

from collections.abc import Mapping

from agentbench.harness import SDK, SuiteRunner
from agentbench.runtime.interception import (
    NullTraceSink,
    TraceSink,
)
from agentbench.sdk.plugins import SDKSelection, evaluation_plan
from agentbench.sdk.runtime import build_evaluation_runner


def build_trace_suite_runner(
    *,
    max_bytes: int,
    model: str | None = None,
    activity_sink: TraceSink | None = None,
    sdk: SDK | None = None,
    sdk_selection: SDKSelection | None = None,
    sdk_options: Mapping[str, object] | None = None,
) -> SuiteRunner:
    sink: TraceSink = activity_sink or NullTraceSink()
    plan = evaluation_plan(
        sdk=sdk,
        selection=sdk_selection,
        options=sdk_options,
    )
    benchmark_runner = build_evaluation_runner(
        plan,
        model=model,
        trace_sink=sink,
        trace_max_bytes=max_bytes,
    )
    return SuiteRunner(benchmark_runner=benchmark_runner)
