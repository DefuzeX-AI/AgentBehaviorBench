"""Concise terminal summaries for SDK evaluation HTTP activity."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentbench.runtime.interception import TraceEvent

from .formatting import case_identity

_OPERATION_PATH = re.compile(r"/operations/[^/]+/?$")


@dataclass(slots=True)
class _PollActivity:
    announced: bool = False
    responses: int = 0


class EvaluationHTTPFormatter:
    """Collapse successful operation polls while keeping SDK failures visible."""

    def __init__(self) -> None:
        self._polls: dict[tuple[str, str, str, str], _PollActivity] = {}

    def reset(self) -> None:
        self._polls.clear()

    def render(self, event: TraceEvent) -> str | None:
        """Return a display line or None for a routine event that can be omitted."""
        data = event.data
        identity = case_identity(data.get("agent_id"), data.get("case_index"), data.get("job_id"))
        method = str(data.get("method") or "?").upper()
        path = str(data.get("path") or "").split("?", 1)[0]
        address = f"{data.get('host') or '?'}{path}"
        call_id = data.get("call_id")
        correlation = f" · call={call_id}" if call_id else ""

        if method == "GET" and _OPERATION_PATH.search(path):
            key = (str(data.get("agent_id") or ""), str(data.get("job_id") or ""),
                   str(data.get("artifact_run_id") or ""), path)
            state = self._polls.setdefault(key, _PollActivity())
            if event.event == "tool_request" and not state.announced:
                state.announced = True
                return f"{identity} SDK operation · polling started"
            if event.event == "tool_response":
                status = data.get("status", "?")
                if _http_failed(status):
                    return f"{identity} SDK operation · HTTP {status}{correlation}"
                state.responses += 1
                if not state.announced:
                    state.announced = True
                    return f"{identity} SDK operation · polling started"
                if _poll_milestone(state.responses):
                    return f"{identity} SDK operation · {state.responses} status checks (HTTP {status})"
            if event.event == "tool_error":
                error = _truncate(str(data.get("error", "Network request failed")), 180)
                return f"{identity} SDK operation · ERROR: {error}{correlation}"
            return None

        target = _truncate(f"{method} {address}", 72)
        if event.event == "tool_response":
            status = data.get("status", "?")
            suffix = correlation if _http_failed(status) else ""
            return f"{identity} SDK API · {target} → HTTP {status}{suffix}"
        if event.event == "tool_error":
            error = _truncate(str(data.get("error", "Network request failed")), 180)
            return f"{identity} SDK API · {target} · ERROR: {error}{correlation}"
        return None


def _http_failed(status: object) -> bool:
    return str(status).isdigit() and int(str(status)) >= 400


def _poll_milestone(count: int) -> bool:
    return count in {10, 25, 50} or (count > 50 and count % 50 == 0)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit - 1] + "…"
