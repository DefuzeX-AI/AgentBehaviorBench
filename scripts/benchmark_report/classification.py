"""Classify pipeline failures and attach saved human review annotations."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any

from .artifacts import load_json, preview


def primary_failure(case: dict[str, Any], manifest: dict[str, Any]) -> tuple[str, str]:
    if case.get("healthy"):
        return ("none", "流水线严格验收通过")
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
        return ("user_cancelled", "用户主动取消")
    if judge == "failed" or any(code in text for code in ("model_invalid_result", "model_output_privacy_rejected", "service_busy", "request_failed")):
        return ("judge_service", "远程 Judge 操作终止，未返回有效报告")
    if "ncbi_query_uri_too_long" in acceptance_codes or "414" in text or "uri too long" in text:
        return ("integration_http_414", "GPT Researcher 的 PMC 请求使用过长 URI，HTTP 414")
    if "multiple values" in text or "prompt_family" in text:
        return ("integration_runtime", "Agent 接入层重复传入 prompt_family，执行失败")
    if "401" in text or "authentication" in text:
        return ("external_auth", "外部模型凭证认证失败，HTTP 401")
    if "immutable" in text or "dict-only" in text or "issue #20" in text:
        return ("bba_trace_mapping", "BBA 把 SDK immutable trace mapping 当作非法 evidence")
    if report_status == "insufficient_evidence":
        return ("judge_insufficient_evidence", "Judge 返回 insufficient_evidence")
    if manifest.get("execution") == "failed":
        return ("integration_runtime", "Agent 执行失败")
    return ("other", preview(error or case.get("failure") or "未分类失败", 220))


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
        reasons.append("同一次 attempt 也发生 GPT Researcher HTTP 414")
    if manifest.get("execution") == "failed" and case.get("judge_status") in {"issue", "insufficient_evidence"}:
        reasons.append("Agent 执行失败，但 Judge 仍返回报告；不能纳入干净能力统计")
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
