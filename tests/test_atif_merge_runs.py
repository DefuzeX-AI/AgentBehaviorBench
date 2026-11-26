"""Recorded OpenClaw chat runs, trimmed to the rows the merge reads (``fixtures/atif/merge/README.md``).

Each run's merged trajectory is compared with the reviewed outline stored beside it.
"""
from datetime import datetime
import json
from pathlib import Path

import pytest

from agentbench.trajectory.atif.attempt import declared_adapters
from agentbench.trajectory.atif.export import build_export
from agentbench.trajectory.atif.slim import check_pointers, stored_document

RUNS = Path(__file__).parent / "fixtures/atif/merge"


def outline(trajectory):
    """The stored trajectory reduced to what the merge decides."""
    steps = []
    for step in trajectory["steps"]:
        abb = (step.get("extra") or {}).get("abb") or {}
        results = (step.get("observation") or {}).get("results") or []
        steps.append({
            "source": step["source"], "message": (step.get("message") or "")[:60], "sources": abb.get("sources"),
            **{key: abb[key] for key in ("owner", "kind") if key in abb},
            **({"tool_calls": [[call["function_name"], ((call.get("extra") or {}).get("abb") or {}).get("sources")]
                               for call in step["tool_calls"]]} if step.get("tool_calls") else {}),
            **({"children": sum(len(result.get("subagent_trajectory_ref") or []) for result in results)}
               if any(result.get("subagent_trajectory_ref") for result in results) else {})})
    return {"agent": trajectory["agent"]["name"], "steps": steps,
            "subagent_trajectories": [outline(child) for child in trajectory.get("subagent_trajectories") or []]}


def merged(directory):
    result, _ = build_export(directory, adapters=declared_adapters(directory))
    stored = stored_document(result.document, directory)
    return result, stored


@pytest.mark.parametrize("name", sorted(path.name for path in RUNS.iterdir() if path.is_dir()))
def test_a_recorded_run_merges_into_its_reviewed_outline(name):
    result, stored = merged(RUNS / name)
    expected = json.loads((RUNS / name / "expected.json").read_text(encoding="utf-8"))
    assert {"status": result.validation["status"], **outline(stored)} == expected
    # Every stored pointer still leads to a recorded line, and steps are dated in order.
    check_pointers(stored, RUNS / name)
    for trajectory in (stored, *stored.get("subagent_trajectories", [])):
        dated = [datetime.fromisoformat(step["timestamp"].replace("Z", "+00:00")) for step in trajectory["steps"]]
        assert dated == sorted(dated)
        assert [step["step_id"] for step in trajectory["steps"]] == list(range(1, len(trajectory["steps"]) + 1))
