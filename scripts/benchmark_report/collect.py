"""Normalize a benchmark campaign ledger into Run and Case attempt records."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Any

from .artifacts import (
    collect_input,
    event_artifact,
    load_json,
    network_summary,
    preview,
    redact,
    relative,
)
from .classification import primary_failure, review_indexes, secondary_failures
from .statistics import summarize

def collect_report(root: Path, ledger_path: Path) -> dict[str, Any]:
    ledger = load_json(ledger_path, {})
    runs = ledger.get("runs", [])
    review_flags, scope_reviews = review_indexes(root)
    cases: list[dict[str, Any]] = []
    generated_failures: list[dict[str, Any]] = []
    generation_skips: list[dict[str, Any]] = []
    run_rows: list[dict[str, Any]] = []

    for run_index, run in enumerate(runs):
        suite_id = str(run.get("suite_id", "unknown"))
        selected = run.get("selected_case_counts") or {
            str(agent): int(run.get("cases_per_agent", 1)) for agent in run.get("agent_ids", [])
        }
        planned = sum(int(v) for v in selected.values())
        attempted = int(run.get("attempted_cases", 1 if run.get("case_id") else 0))
        succeeded = int(run.get("successful_cases", 0))
        if attempted == 0:
            run_status = "preparation_failed"
        elif succeeded == planned and attempted == planned:
            run_status = "complete"
        elif succeeded == 0:
            run_status = "failed"
        else:
            run_status = "partial"
        run_rows.append(
            {
                "index": run_index + 1,
                "suite_id": suite_id,
                "agents": run.get("agent_ids", []),
                "selected_case_counts": selected,
                "planned": planned,
                "generated": int(run.get("generated_cases", 0)),
                "attempted": attempted,
                "healthy": succeeded,
                "status": run_status,
                "qualifying": bool(run.get("qualifying_suite")),
                "artifact": run.get("artifact"),
                "notes": run.get("notes") or run.get("failure") or "",
            }
        )

        # A batch error may fan out to several CaseSkipped result rows. Record the
        # originating preparation error once, then retain skipped slots separately.
        for failure in run.get("preparation_errors", []):
            artifacts = failure.get("artifacts", {}) if isinstance(failure, dict) else {}
            sdk_error = artifacts.get("sdk_error", {}) if isinstance(artifacts, dict) else {}
            if sdk_error.get("code") == "model_output_policy_conflict":
                directory = artifacts.get("directory")
                generated_failures.append(
                    {
                        "suite_id": suite_id,
                        "agent_id": "gpt-researcher",
                        "case_index": None,
                        "category": "case_generation_service",
                        "reason": preview(sdk_error or failure, 300),
                        "artifact_directory": relative(root, Path(directory)) if directory else None,
                    }
                )

        run_cases = run.get("cases")
        if not isinstance(run_cases, list):
            run_cases = [
                {
                    "agent_id": (run.get("agent_ids") or ["unknown"])[0],
                    "case_index": 0,
                    "case_id": run.get("case_id"),
                    "host_accepted": run.get("host_accepted"),
                    "healthy": bool(run.get("host_accepted") and succeeded),
                    "judge_status": run.get("judge_status"),
                    "actual_inputs": run.get("actual_inputs", 0),
                    "artifact_directory": event_artifact(root, run, str(run.get("case_id"))),
                    "error": {"type": "RecordedFailure", "message": run.get("failure")} if run.get("failure") else None,
                }
            ]

        for raw_case in run_cases:
            case_id = raw_case.get("case_id")
            if not case_id:
                error = raw_case.get("error") if isinstance(raw_case.get("error"), dict) else {}
                target = generation_skips if error.get("type") == "CaseSkipped" else generated_failures
                target.append(
                    {
                        "suite_id": suite_id,
                        "agent_id": raw_case.get("agent_id"),
                        "case_index": raw_case.get("case_index"),
                        "category": "case_generation_service",
                        "reason": preview(raw_case.get("error") or "CaseGen 未生成 Case", 300),
                        "artifact_directory": raw_case.get("artifact_directory"),
                    }
                )
                continue
            artifact_rel = raw_case.get("artifact_directory") or event_artifact(root, run, str(case_id))
            artifact_dir = root / str(artifact_rel) if artifact_rel else Path()
            manifest = load_json(artifact_dir / "evaluation/manifest.json", {}) if artifact_rel else {}
            report = load_json(artifact_dir / "evaluation/judge/report.json", None) if artifact_rel else None
            case_json = load_json(artifact_dir / "evaluation/case.json", {}) if artifact_rel else {}
            input_dirs = sorted((artifact_dir / "evaluation/inputs").glob("[0-9][0-9][0-9][0-9]")) if artifact_rel else []
            item = dict(raw_case)
            item["healthy"] = bool(raw_case.get("healthy", raw_case.get("host_accepted") and succeeded))
            category, label = primary_failure(item, manifest)
            public_case = (
                case_json.get("extensions", {}).get("official_case", {}).get("public_case", {})
                if isinstance(case_json, dict)
                else {}
            )
            cases.append(
                {
                    **item,
                    "run_index": run_index + 1,
                    "suite_id": suite_id,
                    "artifact_directory": relative(root, artifact_dir) if artifact_rel else None,
                    "manifest": manifest,
                    "case": redact(case_json),
                    "title": public_case.get("title") or str(case_id),
                    "description": public_case.get("description") or "",
                    "judge_report": redact(report),
                    "judge_status": (report or {}).get("status") if isinstance(report, dict) else raw_case.get("judge_status"),
                    "failure_category": category,
                    "failure_label": label,
                    "secondary_failures": secondary_failures(item, manifest),
                    "review_flags": review_flags.get(str(case_id), []),
                    "scope_review": scope_reviews.get(str(case_id)),
                    "inputs": [collect_input(root, directory) for directory in input_dirs],
                    "network": network_summary(artifact_dir / "network.jsonl") if artifact_rel else {},
                    "raw_files": {
                        name: relative(root, artifact_dir / name)
                        for name in ("evaluation/case.json", "evaluation/manifest.json", "evaluation/judge/report.json", "run.json", "network.jsonl")
                        if (artifact_dir / name).exists()
                    } if artifact_rel else {},
                }
            )

    seen: Counter[str] = Counter()
    for case in cases:
        case_id = str(case.get("case_id"))
        case["attempt_number"] = seen[case_id] + 1
        case["reused"] = seen[case_id] > 0
        seen[case_id] += 1

    # A single preparation failure did not reach CaseGen. Keep it separate from the
    # four service CaseGen failures which appear as case_id=null rows.
    preparation_failures = [row for row in run_rows if row["status"] == "preparation_failed"]
    return summarize(root, ledger, run_rows, cases, generated_failures, generation_skips, preparation_failures)
