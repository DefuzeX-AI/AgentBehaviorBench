"""Minimal replacement evaluator: JSON Inputs with an exact-match Judge.

No KUMA installation, credentials, native history types or container worker.
Adapt a different Case source by implementing the same SDK/Run contract.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4


@dataclass(frozen=True)
class Input:
    input_id: str
    payload: object


@dataclass(frozen=True)
class Report:
    status: str
    confidence: float = 1.0
    issues: tuple[str, ...] = ()
    evidence_gaps: tuple[str, ...] = ()


class Run:
    def __init__(self, inputs: tuple[Input, ...], expected: tuple[object, ...]):
        self.run_id = f"case_file_{uuid4().hex}"
        self.state = "ready"
        self.report: Report | None = None
        self.history: tuple[dict, ...] = ()
        self._inputs = inputs
        self._expected = expected
        self._issues: list[str] = []

    def get_input(self, *, full: bool = False) -> Input | None:
        if not full:
            raise ValueError("Use get_input(full=True)")
        if len(self.history) == len(self._inputs):
            return None
        self.state = "input_delivered"
        return self._inputs[len(self.history)]

    def submit(self, output=None, *, status="completed", error=None) -> Report | None:
        if self.state != "input_delivered":
            raise RuntimeError("Deliver an Input before submitting it once")
        index = len(self.history)
        item = self._inputs[index]
        if status != "completed" or error is not None or output != self._expected[index]:
            self._issues.append(f"Input {item.input_id}: output did not match or execution failed")
        self.history += ({"input_id": item.input_id, "output": output, "status": status},)
        self.state = "ready"
        if len(self.history) == len(self._inputs):
            self.report = Report("issue" if self._issues else "pass", issues=tuple(self._issues))
            self.state = "report_ready"
        return self.report


def create_run(*, repo_path: str | Path, case_file: str | Path) -> Run:
    """Create one fresh Case per call; relative files resolve from the caller's cwd."""

    del repo_path  # This Case source does not inspect the Agent repository.
    data = json.loads(Path(case_file).read_text(encoding="utf-8"))
    rows = data.get("inputs") if isinstance(data, dict) else None
    if not isinstance(rows, list) or not rows:
        raise ValueError("Case file must contain a nonempty inputs array")
    inputs, expected, ids = [], [], set()
    for row in rows:
        if not isinstance(row, dict) or not {"input_id", "payload", "expected_output"} <= row.keys():
            raise ValueError("Each Input needs input_id, payload and expected_output")
        identifier = row["input_id"]
        if not isinstance(identifier, str) or not identifier.strip() or identifier in ids:
            raise ValueError("Input IDs must be nonempty unique strings")
        ids.add(identifier)
        inputs.append(Input(identifier, row["payload"]))
        expected.append(row["expected_output"])
    return Run(tuple(inputs), tuple(expected))
