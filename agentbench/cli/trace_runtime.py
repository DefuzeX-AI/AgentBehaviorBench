"""Build benchmark runners with model interception trace output."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from agentbench.harness import SDK, SuiteRunner
from agentbench.runtime.interception import (
    NullTraceSink,
    TerminalTraceSink,
    TraceEvent,
    TraceSink,
)
from agentbench.sdk.plugins import SDKSelection, evaluation_plan
from agentbench.sdk.runtime import build_evaluation_runner


def build_trace_suite_runner(
    *,
    mode: str,
    max_bytes: int,
    output_fn: Callable[[str], None],
    model: str | None = None,
    activity_sink: TraceSink | None = None,
    sdk: SDK | None = None,
    sdk_selection: SDKSelection | None = None,
    sdk_options: Mapping[str, object] | None = None,
) -> SuiteRunner:
    if mode not in {"off", "terminal"}:
        raise ValueError(f"Unsupported LLM trace mode: {mode!r}")
    sinks: list[TraceSink] = []
    if activity_sink is not None:
        sinks.append(activity_sink)
    if mode == "terminal":
        trace_output = getattr(activity_sink, "write_static", output_fn)
        sinks.append(TerminalTraceSink(trace_output))
    sink: TraceSink = _CompositeTraceSink(tuple(sinks)) if sinks else NullTraceSink()
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


class _CompositeTraceSink:
    def __init__(self, sinks: tuple[TraceSink, ...]) -> None:
        self._sinks = sinks

    def emit(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)
