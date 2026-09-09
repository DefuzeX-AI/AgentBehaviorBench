"""Build benchmark runners with model interception trace output."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from agentbench.harness import SDK, AgentRunner, BenchmarkRunner, SuiteRunner
from agentbench.runtime import RuntimeFactory
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.interception import (
    NullTraceSink,
    OpenRouterProvider,
    TerminalTraceSink,
    TraceEvent,
    TraceSink,
)


def build_trace_suite_runner(
    *,
    mode: str,
    max_bytes: int,
    output_fn: Callable[[str], None],
    model: str | None = None,
    activity_sink: TraceSink | None = None,
    sdk: SDK | None = None,
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
    runtime_factory = RuntimeFactory(
        docker_builder=lambda: DockerRuntime(
            model_provider=OpenRouterProvider(model=model),
            trace_sink=sink,
            trace_max_bytes=max_bytes,
        )
    )
    agent_runner = AgentRunner(runtime_factory=runtime_factory)
    if sdk is None:
        from agentbench.sdk.defuzex import cli_options

        sdk_options = cli_options(sdk_options)
    benchmark_runner = BenchmarkRunner(
        agent_runner=agent_runner,
        sdk=sdk,
        sdk_options=sdk_options,
    )
    return SuiteRunner(benchmark_runner=benchmark_runner)


class _CompositeTraceSink:
    def __init__(self, sinks: tuple[TraceSink, ...]) -> None:
        self._sinks = sinks

    def emit(self, event: TraceEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)
