"""Concise terminal summaries for SDK evaluation HTTP activity."""

from __future__ import annotations

import re
from dataclasses import dataclass

from agentbench.runtime.interception import TraceEvent

from .formatting import case_identity
from .generation_progress import GenerationProgress, read_generation_progress

_OPERATION_PATH = re.compile(r"/operations/[^/]+/?$")


@dataclass(slots=True)
class _PollActivity:
    announced: bool = False
    responses: int = 0


class EvaluationHTTPFormatter:
    """Collapse successful operation polls while keeping SDK failures visible."""

    def __init__(self) -> None:
        self._polls: dict[tuple[str, str, str, str], _PollActivity] = {}
        self._generation_operations: dict[tuple[str, str], GenerationProgress] = {}
        self._announced_generation_cases: set[tuple[str, int]] = set()

    def reset(self) -> None:
        self._polls.clear()
        self._generation_operations.clear()
        self._announced_generation_cases.clear()

    def render(self, event: TraceEvent) -> str | None:
        """Return a display line or None for a routine event that can be omitted."""
        data = event.data
        method = str(data.get("method") or "?").upper()
        path = str(data.get("path") or "").split("?", 1)[0]
        address = f"{data.get('host') or '?'}{path}"
        call_id = data.get("call_id")
        correlation = f" · call={call_id}" if call_id else ""
        generation = self._generation_context(data, method, path)
        identity = (case_identity(data.get("agent_id"), generation.active_index, data.get("job_id"),
                                  generation.total)
                    if generation is not None and generation.active_index is not None
                    else case_identity(data.get("agent_id"), data.get("case_index"), data.get("job_id")))

        if method == "GET" and _OPERATION_PATH.search(path):
            key = (str(data.get("agent_id") or ""), str(data.get("job_id") or ""),
                   str(data.get("artifact_run_id") or ""), path)
            state = self._polls.setdefault(key, _PollActivity())
            if event.event == "tool_request" and not state.announced:
                state.announced = True
                label = "Waiting for SDK" if generation is not None else "SDK operation · polling started"
                return f"{identity} {label}"
            if event.event == "tool_response":
                status = data.get("status", "?")
                if _http_failed(status):
                    return f"{identity} SDK operation · HTTP {status}{correlation}"
                state.responses += 1
                if not state.announced:
                    state.announced = True
                    label = "Waiting for SDK" if generation is not None else "SDK operation · polling started"
                    return f"{identity} {label}"
                if _poll_milestone(state.responses):
                    label = (f"Still waiting · {state.responses} checks" if generation is not None else
                             f"SDK operation · {state.responses} status checks (HTTP {status})")
                    return f"{identity} {label}"
            if event.event == "tool_error":
                error = _truncate(str(data.get("error", "Network request failed")), 180)
                return f"{identity} SDK operation · ERROR: {error}{correlation}"
            return None

        if (data.get("phase") == "generate" and generation is not None
                and generation.active_index is not None and method not in {"GET", "?"}
                and event.event == "tool_request"):
            key = (str(data.get("artifact_directory")), generation.active_index)
            if key not in self._announced_generation_cases:
                self._announced_generation_cases.add(key)
                progress = f"{generation.ready}/{generation.total} saved"
                if generation.failed:
                    progress += f" · {generation.failed} failed"
                return f"{identity} Generating · {progress}"

        target = _truncate(f"{method} {address}", 72)
        if event.event == "tool_response":
            status = data.get("status", "?")
            if data.get("phase") == "generate" and _http_success(status):
                return None
            suffix = correlation if _http_failed(status) else ""
            return f"{identity} SDK API · {target} → HTTP {status}{suffix}"
        if event.event == "tool_error":
            error = _truncate(str(data.get("error", "Network request failed")), 180)
            return f"{identity} SDK API · {target} · ERROR: {error}{correlation}"
        return None

    def _generation_context(self, data, method: str, path: str) -> GenerationProgress | None:
        if data.get("phase") != "generate":
            return None
        current = read_generation_progress(data)
        if method != "GET" or not _OPERATION_PATH.search(path):
            return current
        key = (str(data.get("artifact_directory") or ""), path)
        previous = self._generation_operations.get(key)
        if previous is not None:
            return previous
        if current is not None and current.active_index is not None:
            self._generation_operations[key] = current
        return current


def _http_failed(status: object) -> bool:
    return str(status).isdigit() and int(str(status)) >= 400


def _http_success(status: object) -> bool:
    return str(status).isdigit() and 200 <= int(str(status)) < 400


def _poll_milestone(count: int) -> bool:
    return count in {10, 25, 50} or (count > 50 and count % 50 == 0)


def _truncate(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[:limit - 1] + "…"
