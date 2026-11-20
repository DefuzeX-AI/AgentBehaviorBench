"""ATIF clocks use a unique native OTel span, never its journal arrival time."""
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import PurePosixPath

from agentbench.observe.tool_links import compatible
from .contracts import EvidenceIssue

_EPOCH = datetime(1970, 1, 1, tzinfo=timezone.utc)


def _instant(span):
    value = span.get("start_time")
    if not isinstance(value, str):
        return None
    try:
        start = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if start.tzinfo is None:
            return None
        elapsed = start - _EPOCH
        micros = (elapsed.days * 86400 + elapsed.seconds) * 1000000 + elapsed.microseconds
        # The SDK's text representation can round to microseconds. Prefer its
        # original integer clock for ordering sub-microsecond starts.
        nanos = span.get("start_time_unix_nano")
        return value, int(nanos) if nanos is not None else micros * 1000
    except (ValueError, TypeError, OverflowError):
        return None


class SpanTimes:
    def __init__(self, bundle, issues):
        self.by_operation = defaultdict(list)
        self.issues = issues
        for ref in bundle.raw_records:
            if PurePosixPath(ref["file"]).name not in ("otel.jsonl", "otel-live.jsonl"):
                continue
            row = ref["raw"]
            if not isinstance(row, dict) or row.get("source") != "otel" or row.get("event") != "span":
                continue
            span = row.get("data")
            if not isinstance(span, dict) or not isinstance(span.get("attributes"), dict):
                continue
            attrs = span["attributes"]
            invocation = attrs.get("abb.invocation_id")
            trace, sid = span.get("trace_id"), span.get("span_id")
            instant = _instant(span)
            if not all(isinstance(x, str) and x for x in (invocation, trace, sid)) or instant is None:
                continue
            framework = attrs.get("abb.framework_span_id")
            if framework is None:
                if span.get("name") != "abb.execute" or span.get("parent_span_id"):
                    continue
            elif not isinstance(framework, str):
                continue
            scope = {k: attrs.get("abb." + k) for k in ("input_id", "case_id", "agent_id")}
            scope["run_id"] = row.get("run_id")
            self.by_operation[invocation, framework].append((scope, (trace, sid), instant, ref))

    def start(self, scope, framework=None):
        matches = {}
        for saved, identity, (when, ns), ref in self.by_operation.get((scope.get("invocation_id"), framework), []):
            if compatible(saved, scope, scope_keys=("run_id", "case_id", "input_id", "agent_id")):
                matches.setdefault((*identity, ns), {"start_time": when, "unix_nano": ns,
                                                     "file": ref["file"], "line": ref["line"]})
        if len(matches) == 1:
            return next(iter(matches.values()))
        if matches:
            self.issues.append(EvidenceIssue("ambiguous_otel_clock", "Multiple OTel span boundaries match this identity",
                                             [scope["invocation_id"]]))
        return None
