"""Official container-local KUMA evaluation adapter."""

from __future__ import annotations

from collections.abc import Mapping

from ...contracts import EvaluationRunner, RunnerConcurrencyCapabilities, SDKRunnerContext


class KumaEvaluationSDK:
    """Strategy adapter for the existing formal KUMA container runner."""

    execution = "container"
    concurrency_capabilities = RunnerConcurrencyCapabilities(
        isolated_cases=True, cooperative_cancel=True,
    )

    def create_benchmark_runner(
        self, *, context: SDKRunnerContext, options: Mapping[str, object]
    ) -> EvaluationRunner:
        from .benchmark import KumaContainerRunner

        # getting .env
        environment = dict(context.environ)

        if context.model is not None:
            environment["OPENROUTER_MODEL"] = context.model

        return KumaContainerRunner(
            environ=environment,
            options=options,
            trace_sink=context.trace_sink,
            trace_max_bytes=context.trace_max_bytes,
            control=context.control,
            build_coordinator=context.build_coordinator,
            job_context=context.job_context,
            runtime_services=context.runtime_services,
        )


plugin = KumaEvaluationSDK()
