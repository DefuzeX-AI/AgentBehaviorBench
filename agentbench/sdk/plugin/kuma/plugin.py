"""Official container-local KUMA evaluation adapter."""

from __future__ import annotations

from collections.abc import Mapping

from ...contracts import EvaluationRunner, RunnerConcurrencyCapabilities, SDKRunnerContext


class KumaEvaluationSDK:
    """Strategy adapter for the existing formal KUMA container runner."""

    execution = "container"

    def version_info(self):
        # Complete the public check before catalog transport can schedule an
        # asynchronous stderr reminder. The SDK cache deduplicates later checks.
        from kuma import check_for_updates
        result = check_for_updates()
        return {'name': 'KUMA', 'version': result['current_version'],
                'latest_version': result['latest_version']
                if result['status'] in {'required', 'optional'} else None}

    def strategy_selection(self, directory):
        from .strategy_checks import selection
        return selection(directory)

    def strategy_checker(self, *, environ, timeout):
        from .strategy_checks import checker
        return checker(environ=environ, timeout=timeout)
    concurrency_capabilities = RunnerConcurrencyCapabilities(
        isolated_cases=True, cooperative_cancel=True,
    )

    def onboarding_requirements(self) -> str:
        from .onboarding import REQUIREMENTS
        return REQUIREMENTS

    def validate_onboarding(self, directory) -> None:
        from .onboarding import validate
        validate(directory)

    def onboarding_context(self, *, environ, timeout):
        from .onboarding_catalog import fetch
        return fetch(environ=environ, timeout=timeout)

    def configured_onboarding_context(self, *, environ, timeout, evaluation):
        from .onboarding_catalog import fetch
        return fetch(environ=environ, timeout=timeout, evaluation=evaluation)

    def validate_onboarding_context(self, directory, *, context):
        from .onboarding_catalog import validate_selection
        validate_selection(directory, context=context)

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
