"""Rebuild from source to verify an export; never trust its own success flag."""
from pathlib import Path
import json


def verify(directory, exported):
    from agentbench.trajectory.atif.export import build_export
    root = Path(exported)
    manifest = json.loads((root / "export-manifest.json").read_text(encoding="utf-8"))
    result, bundle = build_export(directory, adapters=manifest["adapters"], allow_incomplete=manifest["allow_incomplete"])
    checks = {"trajectory_matches_rebuild": result.document.to_json_dict() == json.loads((root / "trajectory.atif.json").read_text(encoding="utf-8")),
        "source_digests_match": result.manifest["sources"] == manifest["sources"],
        "association_matches_rebuild": result.association == json.loads((root / "association-report.json").read_text(encoding="utf-8"))}
    content = content_checks(bundle, result.document)
    return {"passed": all(checks.values()) and all(c["passed"] for c in content), "checks": checks,
            "content_checks": content, "coverage": result.validation}


from agentbench.trajectory.atif.validation import content_checks


def live_checks(directory, result, case):
    root = Path(directory)
    run = json.loads((root / "run.json").read_text(encoding="utf-8"))
    checks = {"official_schema": result.validation["official_schema_valid"],
              "records_conserved": result.validation["evidence_conserved"],
              "cleanup_completed": run.get("cleanup_status") == "completed"}
    if case.get("cancel_after_deltas"):
        checks["cancelled_after_saved_delta"] = run["status"] == "cancelled" and run.get("observed_deltas", 0) >= case["cancel_after_deltas"]
        checks["partial_evidence_reported"] = result.validation["status"] == "partial"
        return checks
    checks["agent_succeeded"] = run["status"] == "succeeded"
    checks["minimum_children"] = result.validation["embedded_children"] >= case.get("minimum_children", 0)
    checks["minimum_delegations"] = max(len(result.association["delegations"]), len(result.association["delegation_facts"])) >= case.get("minimum_delegations", 0)
    checks["tools_observed"] = result.validation["observed_tools"] > 0
    workspace = root / "actual-files"
    for expectation in case.get("files", []):
        path = workspace / expectation["path"]
        if not path.resolve().is_relative_to(workspace.resolve()) or path.is_symlink():
            raise ValueError("Expected artifact escapes experiment workspace")
        checks["file:" + expectation["path"]] = path.is_file() and path.read_text(encoding="utf-8") == expectation["content"]
    for relative in case.get("absent_files", []):
        path = workspace / relative
        if not path.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("Expected artifact escapes experiment workspace")
        checks["absent:" + relative] = not path.exists()
    return checks
