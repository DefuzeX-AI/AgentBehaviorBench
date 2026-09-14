"""Provider-independent interfaces implemented by evaluation SDK adapters.

This module uses only the standard library. Importing a contract must never
import an evaluator, discover plugins, or require an evaluator's dependencies.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal, Protocol, runtime_checkable

if TYPE_CHECKING:
    from agentbench.harness.registry import AgentRegistration
    from agentbench.harness.result import BenchmarkResult


SDK_PLUGIN_API_VERSION = "agentbench.evaluation_sdk.v1"


@dataclass(frozen=True, slots=True)
class SDKReference:
    """Identity of an SDK, without importing or initializing its implementation.

    For discovered adapters, ``name`` is the directory name and ``object_ref``
    is the qualified ``plugin`` export. Python injection is an explicit caller
    override, not an additional source of discoverable adapters.
    """

    name: str
    source: Literal["directory", "python"]
    object_ref: str


class SDKReport(Protocol):
    status: str
    confidence: object
    issues: tuple[object, ...]
    evidence_gaps: tuple[object, ...]


class SDKTestInput(Protocol):
    input_id: str
    payload: object


class SDKRun(Protocol):
    """One Case: deliver an Input, submit once, then advance or expose a report.

    History entries belong to the adapter; the host runner only counts them.
    No KUMA state objects, submission extensions, or private fields are required.
    """

    run_id: str
    state: str
    report: SDKReport | None
    history: tuple[object, ...]

    def get_input(self, *, full: bool = False) -> SDKTestInput | None: ...

    def submit(
        self, output: object = None, *, status: str = "completed",
        error: str | None = None,
    ) -> SDKReport | None: ...


class SDKRunFactory(Protocol):
    def __call__(self, **kwargs: object) -> SDKRun: ...


class SDK(Protocol):
    """A module or configured object receiving repo_path plus its own options."""

    def create_run(self, **kwargs: object) -> SDKRun: ...


class EvaluationRunner(Protocol):
    """Strategy that validates and evaluates one registered Agent."""

    def validate_sdk(self, registration: AgentRegistration) -> str: ...

    def run(
        self, registration: AgentRegistration, **kwargs: object,
    ) -> BenchmarkResult: ...


@dataclass(frozen=True, slots=True)
class SDKRunnerContext:
    """Host facilities available to a plugin's runner factory."""

    environ: Mapping[str, str]
    model: str | None
    trace_sink: object
    trace_max_bytes: int


@runtime_checkable
class EvaluationSDKPlugin(Protocol):
    """Directory adapter owning an SDK's dependencies and execution loop.

    Export an instance as ``plugin`` from ``sdk/<name>/plugin.py``. The directory
    supplies its name; no duplicate registration or name field is required.
    Importing the entry module must not start work or require SDK dependencies.
    """

    api_version: str
    execution: Literal["container", "local"]

    def create_benchmark_runner(
        self, *, context: SDKRunnerContext, options: Mapping[str, object],
    ) -> EvaluationRunner: ...
