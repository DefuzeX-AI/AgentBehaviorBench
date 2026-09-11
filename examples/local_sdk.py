"""Deterministic, credential-free SDK used for local development."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True, slots=True)
class Input:
    input_id: str
    payload: object


@dataclass(frozen=True, slots=True)
class Report:
    status: str
    confidence: float
    issues: tuple[object, ...] = ()
    evidence_gaps: tuple[object, ...] = ()


class Run:
    def __init__(self, *, expected: object) -> None:
        self.run_id = f"local_{uuid4().hex}"
        self.state = "ready"
        self.report: Report | None = None
        self.history: tuple[object, ...] = ()
        self._input = Input(f"input_{uuid4().hex}", expected)
        self._pending = True
        self._expected = expected

    def get_input(self, *, full: bool = False) -> Input | None:
        if not full:
            raise ValueError("This example requires get_input(full=True)")
        if not self._pending:
            return None
        self.state = "input_delivered"
        return self._input

    def submit(
        self,
        output: object = None,
        *,
        status: str = "completed",
        error: str | None = None,
    ) -> Report:
        if not self._pending:
            raise RuntimeError("The input has already been submitted")
        self._pending = False
        passed = status == "completed" and error is None and output == self._expected
        self.history = (
            {"input_id": self._input.input_id, "status": status, "output": output},
        )
        self.report = Report(
            status="pass" if passed else "issue",
            confidence=1.0,
            issues=() if passed else ("Output did not equal the expected value",),
        )
        self.state = "report_ready"
        return self.report


def create_run(
    *, repo_path: str | Path, expected: object = "DEFUZEX_AGENT_READY"
) -> Run:
    """Create a fresh case; repo_path is accepted as required by ABB."""

    del repo_path
    return Run(expected=expected)
