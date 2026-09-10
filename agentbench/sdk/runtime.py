"""Create an evaluation runner from a normalized SDK plan."""

from __future__ import annotations

import os

from agentbench.harness import AgentRunner, BenchmarkRunner
from agentbench.harness.errors import ProviderSelectionError
from agentbench.harness.protocols.evaluation import EvaluationRunner
from agentbench.runtime import RuntimeFactory
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.interception import OpenRouterProvider

from .plugins import (
    EvaluationPlan,
    EvaluationSDKPlugin,
    SDKRunnerContext,
    plugin_execution,
)


def build_evaluation_runner(
    plan: EvaluationPlan,
    *,
    model: str | None,
    trace_sink: object,
    trace_max_bytes: int,
) -> EvaluationRunner:
    """Build the selected runner without leaking selection into orchestration."""

    selected = plan.selection.value
    context = SDKRunnerContext(
        environ=dict(os.environ),
        model=model,
        trace_sink=trace_sink,
        trace_max_bytes=trace_max_bytes,
    )
    execution = plugin_execution(selected)
    if isinstance(selected, EvaluationSDKPlugin):
        runner = selected.create_benchmark_runner(
            context=context,
            options=plan.options,
        )
        if not callable(getattr(runner, "validate_sdk", None)) or not callable(
            getattr(runner, "run", None)
        ):
            raise ProviderSelectionError(
                "SDK plugin create_benchmark_runner() returned an invalid runner"
            )
        return runner

    if execution != "local":
        raise ProviderSelectionError(
            "A plain create_run SDK can only execute in the host process"
        )
    runtime_factory = RuntimeFactory(
        docker_builder=lambda: DockerRuntime(
            model_provider=OpenRouterProvider(model=model),
            trace_sink=trace_sink,  # type: ignore[arg-type]
            trace_max_bytes=trace_max_bytes,
        )
    )
    return BenchmarkRunner(
        agent_runner=AgentRunner(runtime_factory=runtime_factory),
        sdk=selected,  # type: ignore[arg-type]
        sdk_options=plan.options,
    )
