"""Create an evaluation runner from a normalized SDK plan."""

from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from types import MappingProxyType

from agentbench.harness import AgentRunner, BenchmarkRunner
from agentbench.harness.errors import ProviderSelectionError
from agentbench.runtime import RuntimeFactory
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.interception import OpenRouterProvider

from .contracts import EvaluationRunner, EvaluationSDKPlugin, SDKRunnerContext
from .plugins import EvaluationPlan, plugin_execution

def build_evaluation_runner(
    plan: EvaluationPlan,
    *,
    model: str | None,
    trace_sink: object,
    trace_max_bytes: int,
    environ: Mapping[str, str] | None = None,
    control=None,
    build_coordinator=None,
    job_context: Mapping[str, object] | None = None,
    runtime_services=None,
) -> EvaluationRunner:
    """Build the selected runner without leaking selection into orchestration."""

    selected = plan.selection.value
    context = SDKRunnerContext(
        environ=MappingProxyType(dict(os.environ if environ is None else environ)),
        model=model,
        trace_sink=trace_sink,
        trace_max_bytes=trace_max_bytes,
        control=control,
        build_coordinator=build_coordinator,
        job_context=MappingProxyType(dict(job_context or {})),
        runtime_services=runtime_services,
    )

    execution = plugin_execution(selected)
    if isinstance(selected, EvaluationSDKPlugin):
        try:
            runner = selected.create_benchmark_runner(
                context=context,
                options=plan.options,
            )
        except ModuleNotFoundError as exc:
            raise ProviderSelectionError(
                f"Could not create SDK {plan.selection.reference.name!r} runner: "
                f"missing module {exc.name!r}. Check the adapter's dependencies."
            ) from exc
        if not all(callable(getattr(runner, method, None))
                   for method in ('validate_sdk', 'prepare_cases', 'run_case')):
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
            environ=context.environ,
            control=control,
            build_coordinator=build_coordinator,
            identity=job_context,
            model_provider=OpenRouterProvider(model=model),
            trace_sink=trace_sink,  # type: ignore[arg-type]
            trace_max_bytes=trace_max_bytes,
        )
    )
    from agentbench.observe.host import host_observation_factory
    return BenchmarkRunner(
        observation_factory=host_observation_factory(Path.cwd() / "results" / "observe"),
        agent_runner=AgentRunner(runtime_factory=runtime_factory),
        sdk=selected,  # type: ignore[arg-type]
        sdk_options=plan.options,
        environ=context.environ,
        control=control,
    )

class EvaluationRunnerFactory:
    """Immutable selection/environment; mutable runtime services belong to a suite."""

    def __init__(self, plan, *, model, trace_sink, trace_max_bytes, environ=None):
        self.plan = plan
        self.model = model
        self.trace_sink = trace_sink
        self.trace_max_bytes = trace_max_bytes
        self.environ = MappingProxyType(dict(os.environ if environ is None else environ))
        capabilities = getattr(plan.selection.value, 'concurrency_capabilities', None)
        self.supports_concurrency = (
            isinstance(plan.selection.value, EvaluationSDKPlugin)
            and getattr(capabilities, 'isolated_cases', False) is True
            and getattr(capabilities, 'cooperative_cancel', False) is True
        )

    def open_suite(self, suite_id, control):
        return SuiteRunnerFactory(self, suite_id, control)

class SuiteRunnerFactory:
    """One build coordinator per suite, one independent runner per preparation or Case job."""

    def __init__(self, factory, suite_id, control):
        from agentbench.runtime.services import RuntimeServices

        self.factory = factory
        self.suite_id = suite_id
        self.control = control
        self.runtime_services = RuntimeServices(environ=factory.environ)
        self._closed = False

    def create(self, registration, job_context, trace_sink=None):
        if self._closed:
            raise RuntimeError('Cannot create an evaluation runner after the suite has closed')
        if self.control is not None:
            self.control.check()
        identity = {**dict(job_context or {}), 'suite_id': self.suite_id,
                    'agent_id': registration.agent_id}
        return build_evaluation_runner(
            self.factory.plan, model=self.factory.model,
            trace_sink=self.factory.trace_sink if trace_sink is None else trace_sink,
            trace_max_bytes=self.factory.trace_max_bytes, environ=self.factory.environ,
            control=self.control,
            build_coordinator=self.runtime_services.build_coordinator,
            job_context=identity, runtime_services=self.runtime_services,
        )

    def close(self):
        if not self._closed:
            self._closed = True
            self.runtime_services.close()

def build_evaluation_runner_factory(
    plan: EvaluationPlan, *, model: str | None, trace_sink: object,
    trace_max_bytes: int, environ: Mapping[str, str] | None = None,
) -> EvaluationRunnerFactory:
    return EvaluationRunnerFactory(
        plan, model=model, trace_sink=trace_sink, trace_max_bytes=trace_max_bytes,
        environ=environ,
    )
