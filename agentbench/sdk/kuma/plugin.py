"""Official container-local KUMA evaluation adapter."""

from __future__ import annotations

from collections.abc import Mapping

from agentbench.harness.protocols.evaluation import EvaluationRunner

from ..plugins import SDK_PLUGIN_API_VERSION, SDKRunnerContext


class KumaEvaluationSDK:
    """Strategy adapter for the existing formal KUMA container runner."""

    name = "kuma"
    api_version = SDK_PLUGIN_API_VERSION
    execution = "container"

    def create_benchmark_runner(
        self, *, context: SDKRunnerContext, options: Mapping[str, object]
    ) -> EvaluationRunner:
        from .benchmark import KumaContainerRunner

        environment = dict(context.environ)
        if context.model is not None:
            environment["OPENROUTER_MODEL"] = context.model
        return KumaContainerRunner(
            environ=environment,
            options=options,
            trace_sink=context.trace_sink,
            trace_max_bytes=context.trace_max_bytes,
        )


plugin = KumaEvaluationSDK()
