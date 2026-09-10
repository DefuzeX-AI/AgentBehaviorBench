"""Runner interface used by the benchmark suite orchestration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

if TYPE_CHECKING:
    from ..registry import AgentRegistration
    from ..result import BenchmarkResult


class EvaluationRunner(Protocol):
    """Strategy that validates and evaluates one registered Agent."""

    def validate_sdk(self, registration: "AgentRegistration") -> str: ...

    def run(
        self, registration: "AgentRegistration", **kwargs: object
    ) -> "BenchmarkResult": ...
