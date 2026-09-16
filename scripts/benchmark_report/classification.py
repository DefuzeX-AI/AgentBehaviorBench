"""Classify pipeline failures and attach saved human review annotations."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .artifacts import load_json, preview


def primary_failure(case: dict[str, Any], manifest: dict[str, Any]) -> tuple[str, str]:
    if case.get("healthy"):
        return ("none", "Passed strict pipeline acceptance")
    error = case.get("error") if isinstance(case.get("error"), dict) else {}
    text = " ".join(str(v) for v in (error.get("type"), error.get("message"), case.get("failure")) if v).lower()
    acceptance_codes = {
        str(item.get("code"))
        for item in case.get("acceptance_errors", [])
        if isinstance(item, dict) and item.get("code")
    }
    judge = manifest.get("judge")
    report_status = case.get("judge_status")
    if "cancel" in text:
        return ("user_cancelled", "Cancelled by the user")
    if judge == "failed" or any(code in text for code in ("model_invalid_result", "model_output_privacy_rejected", "service_busy", "request_failed")):
        return ("judge_service", "The remote Judge operation ended without a valid report")
    if "ncbi_query_uri_too_long" in acceptance_codes or "414" in text or "uri too long" in text:
        return ("integration_http_414", "GPT Researcher used an overlong URI for a PMC request (HTTP 414)")
    if "multiple values" in text or "prompt_family" in text:
        return ("integration_runtime", "The Agent integration passed prompt_family twice and execution failed")
    if "401" in text or "authentication" in text:
        return ("external_auth", "External model credential authentication failed (HTTP 401)")
    if "immutable" in text or "dict-only" in text or "issue #20" in text:
        return ("bba_trace_mapping", "BBA treated the SDK's immutable trace mapping as invalid evidence")
    if report_status == "insufficient_evidence":
        return ("judge_insufficient_evidence", "Judge returned insufficient_evidence")
    if manifest.get("execution") == "failed":
        return ("integration_runtime", "Agent execution failed")
    return ("other", preview(error or case.get("failure") or "Unclassified failure", 220))


def secondary_failures(case: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    error = case.get("error") if isinstance(case.get("error"), dict) else {}
    text = " ".join(str(v) for v in error.values()).lower()
    acceptance_codes = {
        str(item.get("code"))
        for item in case.get("acceptance_errors", [])
        if isinstance(item, dict) and item.get("code")
    }
    if ("ncbi_query_uri_too_long" in acceptance_codes or "414" in text or "uri too long" in text) and manifest.get("judge") == "failed":
        reasons.append("The same attempt also encountered a GPT Researcher HTTP 414")
    if manifest.get("execution") == "failed" and case.get("judge_status") in {"issue", "insufficient_evidence"}:
        reasons.append("Agent execution failed but the Judge still returned a report; exclude it from clean capability statistics")
    return reasons


def review_indexes(root: Path) -> tuple[dict[str, list[dict[str, Any]]], dict[str, dict[str, Any]]]:
    flags: dict[str, list[dict[str, Any]]] = defaultdict(list)
    live = load_json(root / "docs/Live-Mixed-3x5-2026-09-14.json", {})
    for agent in live.get("agents", []) if isinstance(live, dict) else []:
        for case in agent.get("cases", []):
            if case.get("case_id"):
                flags[str(case["case_id"])].extend(case.get("review_flags", []))
    scopes: dict[str, dict[str, Any]] = {}
    scope = load_json(root / "docs/Case-Scope-Review-2026-09-14.json", {})
    for case in scope.get("cases", []) if isinstance(scope, dict) else []:
        if case.get("case_id"):
            scopes[str(case["case_id"])] = case
    return flags, scopes
