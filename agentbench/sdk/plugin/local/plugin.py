"""Container-local KUMA evaluation with fixed Cases and a local Judge; no Backend."""

from __future__ import annotations

from collections.abc import Mapping

from ...contracts import EvaluationRunner, RunnerConcurrencyCapabilities, SDKRunnerContext


class LocalEvaluationSDK:
    """Run the pinned KUMA SDK with local Case and Judge providers.

    The Agent still runs in its Docker container behind the model interceptor,
    exactly as with ``kuma``. Only Case generation and judging stay local, so a
    run needs no KUMA credential and spends no KUMA credit.
    """

    execution = "container"

    def version_info(self):
        return {'name': 'local', 'version': '0.0.1', 'latest_version': None}

    def strategy_selection(self, directory):
        # Local execution consumes the same KUMA Agent Profile format.
        from ..kuma.strategy_checks import selection
        return selection(directory)

    def strategy_checker(self, *, environ, timeout):
        from .strategy_checks import LocalStrategyChecker
        return LocalStrategyChecker()

    # Selected only by `--sdk local`; an omitted --sdk keeps meaning `kuma`.
    implicit_selection = False
    concurrency_capabilities = RunnerConcurrencyCapabilities(
        isolated_cases=True, cooperative_cancel=True,
    )

    def create_benchmark_runner(
        self, *, context: SDKRunnerContext, options: Mapping[str, object]
    ) -> EvaluationRunner:
        from .benchmark import LocalContainerRunner

        environment = dict(context.environ)
        if context.model is not None:
            environment["OPENROUTER_MODEL"] = context.model

        return LocalContainerRunner(
            environ=environment,
            options=options,
            trace_sink=context.trace_sink,
            trace_max_bytes=context.trace_max_bytes,
            control=context.control,
            build_coordinator=context.build_coordinator,
            job_context=context.job_context,
            runtime_services=context.runtime_services,
        )


plugin = LocalEvaluationSDK()
