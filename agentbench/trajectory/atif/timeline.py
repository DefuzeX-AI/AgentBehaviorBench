"""Order a root execution's steps on the one timeline its merged records share.

Used for sources whose records carry a clock each (``sources/merge.py``). A
user step stands where its prompt was sent, the ACP ``prompt_started`` report,
and every other step where its operation started. Reply text the root session
sent over ACP that no model record carries is a step of its own.
"""
import json

from harbor.models.trajectories import Step

from agentbench.observe.artifact_paths import SESSION_OUTPUT
from .replies import record_turn, turn_scope
from .sources.merge import ACP, clock, reply_segments


def prompt_starts(bundle):
    """When each Input's prompt was sent, by position in ``bundle.inputs``."""
    scopes = [turn_scope(item) for item in bundle.inputs]
    starts = {}
    for event in bundle.native_events:
        if event.get("event") != "prompt_started" or not event.get("evidence"):
            continue
        ref = event["evidence"][0]
        turn = record_turn({**event["data"], "evidence": [ref]}, bundle.inputs, scopes)
        when = clock(event.get("timestamp"))
        if turn is not None and when:
            starts.setdefault(turn, {**when, "file": ref["file"], "line": ref["line"]})
    return starts


def root_sessions(bundle):
    shared = bundle.auxiliary_artifacts.get(SESSION_OUTPUT + "/acp-summary.json") or {}
    sessions = {((item.get("acp_summary") or {}).get("session") or {}).get("sessionId") for item in bundle.inputs}
    sessions.add((shared.get("session") or {}).get("sessionId"))
    return sessions - {None}


def unclaimed_replies(bundle):
    """Reply text of the root session that no model record carries."""
    sessions = root_sessions(bundle)
    claimed = {(ref["file"], ref["line"]) for model in bundle.models if ACP in model.get("sources", ())
               for ref in model["evidence"]}
    return [segment for segment in reply_segments(bundle.native_events)
            if (not sessions or segment["session"] in sessions)
            and (segment["evidence"][0]["file"], segment["evidence"][0]["line"]) not in claimed]


def timeline_steps(bundle, rows, issues):
    """The root steps in timeline order, or None when a prompt's start was not recorded."""
    inputs = bundle.inputs
    starts = prompt_starts(bundle)
    if any(item["record"] is not None and index not in starts for index, item in enumerate(inputs)):
        return None
    entries = []
    for position, (when, rid, step) in enumerate(sorted(rows, key=lambda row: row[:2])):
        entries.append(((when[1], 1, position) if when[0] == 0 else None, step))
    for number, segment in enumerate(unclaimed_replies(bundle)):
        when = segment["clock"]
        entries.append(((when["unix_nano"], 1, len(rows) + number) if when else None,
                        Step(step_id=1, source="agent", message=segment["text"],
                             timestamp=when["start_time"] if when else None,
                             extra={"abb": {"kind": "acp_reply", "evidence": segment["evidence"], "sources": [ACP]}})))
    for index, item in enumerate(inputs):
        if item["record"] is None:
            continue
        payload = item["record"].get("payload")
        prompt = payload if isinstance(payload, str) else "" if payload is None else json.dumps(payload, ensure_ascii=False, sort_keys=True)
        start = starts[index]
        entries.append(((start["unix_nano"], 0, index),
                        Step(step_id=1, source="user", message=prompt, timestamp=start["start_time"],
                             extra={"abb": {"invocation": item, "execution_start": start, "sources": [ACP]}})))
    timed = sorted((entry for entry in entries if entry[0] is not None), key=lambda entry: entry[0])
    # A step without a clock cannot be placed; it follows the timeline in its recorded order.
    return [step for _, step in timed] + [step for moment, step in entries if moment is None]
