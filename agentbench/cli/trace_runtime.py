"""Build benchmark runners with model interception trace output."""

from __future__ import annotations

from collections.abc import Mapping

from agentbench.harness import SDK, SuiteRunner
from agentbench.harness.concurrency import ConcurrencySettings
from agentbench.runtime.interception import (
    NullTraceSink,
    TraceSink,
)
from agentbench.sdk.plugins import SDKSelection, evaluation_plan
from agentbench.sdk.runtime import build_evaluation_runner_factory


def build_trace_suite_runner(
    *,
    max_bytes: int,
    model: str | None = None,
    activity_sink: TraceSink | None = None,
    sdk: SDK | None = None,
    sdk_selection: SDKSelection | None = None,
    sdk_options: Mapping[str, object] | None = None,
    concurrency: ConcurrencySettings | None = None,
    environ: Mapping[str, str] | None = None,
) -> SuiteRunner:
    sink: TraceSink = activity_sink or NullTraceSink()

    # Return the selected SDK implementation.
    # ex:
    #   EvaluationPlan(
    #       selection=SDKSelection(
    #           reference=SDKReference(
    #               name='kuma',
    #               source='directory',
    #               object_ref='agentbench.sdk.plugin.kuma.plugin:plugin'
    #           ),
    #           value=<agentbench.sdk.plugin.kuma.plugin.KumaEvaluationSDK object at 0x...>
    #       ),
    #       options=mappingproxy({})
    #   )
    plan = evaluation_plan(
        sdk=sdk,
        selection=sdk_selection,
        options=sdk_options,
    )

    # Runner instance
    runner_factory = build_evaluation_runner_factory(
        plan,
        model=model,
        trace_sink=sink,
        trace_max_bytes=max_bytes,
        environ=environ,
    )

    return SuiteRunner(runner_factory=runner_factory, concurrency=concurrency, trace_sink=sink)
