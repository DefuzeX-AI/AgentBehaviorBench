"""SDK interfaces consumed by AgentBench."""

from __future__ import annotations

from typing import Protocol


class SDKReport(Protocol):
    """Public report fields consumed by AgentBench."""

    status: str
    confidence: object
    issues: tuple[object, ...]
    evidence_gaps: tuple[object, ...]


class SDKTestInput(Protocol):
    """Public SDK input fields consumed by AgentBench."""

    input_id: str
    payload: object


class SDKRun(Protocol):
    """Input/submission handshake required by the current AgentBench runner."""

    run_id: str
    state: str
    report: SDKReport | None
    history: tuple[object, ...]

    def get_input(self, *, full: bool = False) -> SDKTestInput | None: ...

    def submit(
        self,
        output: object = None,
        *,
        status: str = "completed",
        error: str | None = None,
    ) -> SDKReport | None: ...


class SDKRunFactory(Protocol):
    """Callable shape of ``defuzex.create_run``."""

    def __call__(self, **kwargs: object) -> SDKRun: ...


class SDK(Protocol):
    """A module or object which creates compatible Runs.

    create_run receives the Agent repo_path and user-supplied sdk_options.
    Other SDKs can wrap their own API to return SDKRun-compatible objects.
    """

    def create_run(self, **kwargs: object) -> SDKRun: ...
