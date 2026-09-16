"""Aggregate descriptive benchmark statistics from normalized attempts."""

from __future__ import annotations

import re
from collections import Counter
from datetime import datetime
from pathlib import Path
from statistics import mean, median
from typing import Any

from .artifacts import load_json, percentile, relative, wilson


def summarize(
    root: Path,
    ledger: dict[str, Any],
    runs: list[dict[str, Any]],
    cases: list[dict[str, Any]],
    casegen_failures: list[dict[str, Any]],
    casegen_skips: list[dict[str, Any]],
    preparation_failures: list[dict[str, Any]],
) -> dict[str, Any]:
    healthy = [case for case in cases if case["healthy"]]
    failed = [case for case in cases if not case["healthy"]]
    per_agent: list[dict[str, Any]] = []
    for agent_id in sorted({str(case.get("agent_id")) for case in cases}):
        selected = [case for case in cases if case.get("agent_id") == agent_id]
        passed = sum(bool(case["healthy"]) for case in selected)
        low, high = wilson(passed, len(selected))
        per_agent.append(
            {
                "agent_id": agent_id,
                "attempts": len(selected),
                "unique_cases": len({case.get("case_id") for case in selected}),
                "healthy": passed,
                "rate": passed / len(selected),
                "wilson_low": low,
                "wilson_high": high,
                "judge": dict(Counter(str(case.get("judge_status") or "missing") for case in selected)),
            }
        )

    turn_rows: list[dict[str, Any]] = []
    for turns in sorted({len(case["inputs"]) for case in cases}):
        selected = [case for case in cases if len(case["inputs"]) == turns]
        passed = sum(case["healthy"] for case in selected)
        turn_rows.append({"turns": turns, "attempts": len(selected), "healthy": passed, "rate": passed / len(selected)})

    thirds: list[dict[str, Any]] = []
    for label, start, stop in (("Early", 0, 13), ("Middle", 13, 26), ("Late", 26, 39)):
        selected = [case for case in cases if start <= case["run_index"] - 1 < stop]
        passed = sum(case["healthy"] for case in selected)
        thirds.append({"period": label, "attempts": len(selected), "healthy": passed, "rate": passed / len(selected) if selected else 0})

    duration_by_agent: list[dict[str, Any]] = []
    all_inputs = [(case, inp) for case in cases for inp in case["inputs"]]
    for agent_id in sorted({str(case.get("agent_id")) for case in cases}):
        values = [inp["framework"]["duration_ms"] / 1000 for case, inp in all_inputs if case.get("agent_id") == agent_id and inp["framework"]["duration_ms"] is not None]
        duration_by_agent.append(
            {
                "agent_id": agent_id,
                "n": len(values),
                "median_seconds": median(values) if values else None,
                "mean_seconds": mean(values) if values else None,
                "p90_seconds": percentile(values, 0.9),
                "max_seconds": max(values) if values else None,
            }
        )

    trace_reasons: Counter[str] = Counter()
    input_statuses: Counter[str] = Counter()
    otel_statuses: Counter[str] = Counter()
    total_spans = 0
    framework_spans = 0
    for _, inp in all_inputs:
        input_statuses[str(inp.get("result", {}).get("status") or "missing")] += 1
        otel_statuses[str(inp.get("otel", {}).get("status", {}).get("status") or "missing")] += 1
        total_spans += int(inp.get("otel", {}).get("span_count", 0))
        framework_spans += int(inp.get("framework", {}).get("span_count", 0))
        traces = inp.get("submission", {}).get("capture_status", {}).get("traces", {})
        for reason in traces.get("reasons", []) if isinstance(traces, dict) else []:
            trace_reasons[str(reason)] += 1

    usage = load_json(root / "docs/Campaign-Model-Usage-2026-09-14.json", {})
    live = load_json(root / "docs/Live-Mixed-3x5-2026-09-14.json", {})
    failure_counts = Counter(case["failure_category"] for case in failed)
    judge_counts = Counter(str(case.get("judge_status") or "missing") for case in cases)
    report_cases = [case for case in cases if isinstance(case.get("judge_report"), dict)]
    healthy_judge_counts = Counter(
        str(case.get("judge_status") or "missing") for case in healthy
    )
    judge_service_codes: Counter[str] = Counter()
    for case in failed:
        if case["failure_category"] != "judge_service":
            continue
        error = case.get("error") if isinstance(case.get("error"), dict) else {}
        text = " ".join(str(value) for value in error.values())
        match = re.search(r"\[([a-z][a-z0-9_]*)\]", text)
        judge_service_codes[match.group(1) if match else "unknown"] += 1
    issue_severities = Counter(
        str(issue.get("severity") or "unknown")
        for case in report_cases
        for issue in case["judge_report"].get("issues", [])
    )
    run_counts = Counter(run["status"] for run in runs)
    request_counts: Counter[str] = Counter()
    for source_run in ledger.get("runs", []):
        for name, count in source_run.get("requests", {}).items():
            request_counts[str(name)] += int(count)
    first = [case for case in cases if not case["reused"]]
    reused = [case for case in cases if case["reused"]]
    first_event_date = "unknown"
    if runs and runs[0].get("artifact"):
        first_events = load_json(root / str(runs[0]["artifact"]), [])
        if isinstance(first_events, list) and first_events and first_events[0].get("timestamp"):
            first_event_date = str(first_events[0]["timestamp"])[:10]

    return {
        "meta": {
            "title": "BBA Benchmark Daily Results Analysis",
            "date": first_event_date,
            "generated_at": datetime.now().astimezone().isoformat(),
            "root": str(root.resolve()),
            "ledger": relative(root, root / "docs/Benchmark-Campaign-Ledger.json"),
            "campaign_status": ledger.get("campaign_status"),
            "campaign_stop_reason": ledger.get("campaign_stop_reason"),
        },
        "summary": {
            "runs": len(runs),
            "run_statuses": dict(run_counts),
            "attempts": len(cases),
            "healthy": len(healthy),
            "failed": len(failed),
            "healthy_rate": len(healthy) / len(cases),
            "unique_cases": len({case.get("case_id") for case in cases}),
            "reused_attempts": len(reused),
            "casegen_service_failures": len(casegen_failures),
            "casegen_skipped_slots": len(casegen_skips),
            "preparation_failures": len(preparation_failures),
            "judge_reports": len(report_cases),
            "judge_counts": dict(judge_counts),
            "healthy_judge_counts": dict(healthy_judge_counts),
            "judge_service_codes": dict(judge_service_codes),
            "judge_issue_severities": dict(issue_severities),
            "reports_with_evidence_gaps": sum(
                bool(case["judge_report"].get("evidence_gaps")) for case in report_cases
            ),
            "failure_counts": dict(failure_counts),
            "input_artifacts": len(all_inputs),
            "input_statuses": dict(input_statuses),
            "otel_statuses": dict(otel_statuses),
            "otel_spans": total_spans,
            "framework_spans": framework_spans,
            "trace_reasons": dict(trace_reasons),
            "submitted_steps": sum(bool(inp.get("submission")) for _, inp in all_inputs),
            "trace_partial_steps": sum(
                inp.get("submission", {}).get("capture_status", {}).get("traces", {}).get("status") == "partial"
                for _, inp in all_inputs
            ),
            "requests": dict(request_counts),
            "first_seen": {"attempts": len(first), "healthy": sum(case["healthy"] for case in first)},
            "reused": {"attempts": len(reused), "healthy": sum(case["healthy"] for case in reused)},
        },
        "per_agent": per_agent,
        "by_turns": turn_rows,
        "by_period": thirds,
        "duration_by_agent": duration_by_agent,
        "runs": runs,
        "cases": cases,
        "casegen_failures": casegen_failures,
        "casegen_skips": casegen_skips,
        "preparation_failures": preparation_failures,
        "native_observations": ledger.get("native_observations", []),
        "usage": usage,
        "live_3x5": live,
        "source_documents": [
            path
            for path in (
                "docs/Benchmark-Campaign-Ledger.json",
                "docs/Campaign-Reconciliation-2026-09-14.json",
                "docs/Judge-Failure-Analysis-2026-09-14.json",
                "docs/Judge-Terminal-Errors-2026-09-14.json",
                "docs/Case-Scope-Review-2026-09-14.json",
                "docs/Live-Mixed-3x5-2026-09-14.json",
                "docs/Live-Mixed-3x5-ReAct-Audit-2026-09-14.md",
                "docs/Live-Mixed-3x5-Trading-Audit-2026-09-14.md",
                "docs/Live-Mixed-3x5-GPT-Audit-2026-09-14.md",
                "docs/Trading-CaseGen-Contract-Mismatch-2026-09-14.md",
                "docs/Campaign-Model-Usage-2026-09-14.json",
            )
            if (root / path).exists()
        ],
    }
