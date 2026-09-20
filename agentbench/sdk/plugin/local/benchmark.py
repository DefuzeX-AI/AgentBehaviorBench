"""KUMA's container executor with local providers: no Backend and no KUMA credential."""
from agentbench.harness.errors import ProviderSelectionError
from agentbench.runtime.interception import resolve_model_provider
from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY
from agentbench.sdk.contracts import RunnerRecoveryCapabilities
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner
from agentbench.sdk.plugin.kuma.service import evaluate

from .relay import JudgeRelay, judge_model

# KUMA's evaluation overlay, admitting no Backend egress and forwarding no KUMA variable.
OVERLAY = dict(backend=None, worker_package=__package__, sdk_environment=(), require_profile=False)


class LocalContainerRunner(KumaContainerRunner):
    """Prepare fixed Cases and execute them with the local Judge, as KUMA does."""

    provider_mode = 'local-container'

    def validate_sdk(self, registration):
        try:
            # The Judge still needs its own model, even when observing a native Agent.
            if DEFAULT_ADAPTER_FACTORY.network_mode(getattr(registration, 'framework', 'langgraph')) == 'replace':
                resolve_model_provider(environ=self.environ)
            judge_model(self.environ)
        except ValueError as exc:
            raise ProviderSelectionError(str(exc)) from exc
        return self.provider_mode

    def recovery_capabilities(self, registration) -> RunnerRecoveryCapabilities:
        from agentbench.sdk.common.replay import safe_case_replay
        # A local judgment leaves no Backend request to resume.
        return RunnerRecoveryCapabilities(safe_case_replay(registration), resume_judgment=False)

    def _evaluate(self, registration, **options):
        options.update(require_credentials=False, overlay=OVERLAY)
        if options.get('case_artifact') is None:
            # Case preparation calls no Judge.
            return evaluate(registration, **options)
        model = judge_model(self.environ)
        relays = []
        ready = options.get('on_artifacts_ready')

        def artifacts_ready(directory):
            relays.append(JudgeRelay(directory, model, environ=self.environ).start())
            if ready is not None:
                ready(directory)

        options['on_artifacts_ready'] = artifacts_ready
        try:
            return evaluate(registration, **options)
        finally:
            for relay in relays:
                relay.stop()
