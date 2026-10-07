from __future__ import annotations

import re
from typing import Any

from models.review_schemas import ReviewIssue


_CLAIM_TERM_SPLIT_RE = re.compile(r"[、,，]|以及|及|和|与|并且|并|或")
_TOKEN_SPLIT_RE = re.compile(r"[，。；：、（）\(\)\[\],.;:\s]+")


def _extract_claim_terms_for_zh(text: str) -> list[str]:
    """
    Extract feature-like terms from Chinese claim text.
    Prefer the tail after "包括/包含" to avoid using whole sentence as one token.
    """
    cleaned = text.strip()
    if not cleaned:
        return []

    include_pos = cleaned.find("包括")
    if include_pos < 0:
        include_pos = cleaned.find("包含")
    tail = cleaned[include_pos + 2 :] if include_pos >= 0 else cleaned

    raw_parts = [item.strip() for item in _CLAIM_TERM_SPLIT_RE.split(tail) if item.strip()]
    noise = {"一种", "系统", "方法", "装置", "模块", "单元", "其特征在于", "所述", "用于", "其中"}
    terms: list[str] = []
    for part in raw_parts:
        for token in _TOKEN_SPLIT_RE.split(part):
            token = token.strip()
            if len(token) < 2:
                continue
            if token in noise:
                continue
            terms.append(token)
    return terms


def _find_claim_keywords(claims: dict[str, Any] | None) -> list[str]:
    """
    Build a lightweight keyword set from claim texts for support checks.
    """
    if not claims:
        return []

    keywords: list[str] = []
    claim_items = claims.get("claims")
    if isinstance(claim_items, list):
        iterable = claim_items
    else:
        # Backward compatibility for legacy schema.
        iterable = []
        for group_name in ("independent_claims", "dependent_claims"):
            iterable.extend(claims.get(group_name, []))

    for claim in iterable:
        full_text = str(claim.get("full_text", "")).strip()
        text = full_text or str(claim.get("text", "")).strip()
        if not text:
            continue
        if " " in text:
            for token in text.split():
                token = token.strip()
                if len(token) >= 4:
                    keywords.append(token)
        else:
            keywords.extend(_extract_claim_terms_for_zh(text))
    # Keep deterministic order while de-duplicating.
    deduped: list[str] = []
    seen = set()
    for kw in keywords:
        if kw in seen:
            continue
        seen.add(kw)
        deduped.append(kw)
    return deduped


def logic_consistency_review(
    *,
    claims: dict[str, Any] | None,
    specification: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Check whether specification appears to support claim features.
    Emits ReviewIssue list as dict payloads for workflow compatibility.
    """
    issues: list[dict[str, Any]] = []
    if not claims or not specification:
        return issues

    def _flatten_text(value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, dict):
            out: list[str] = []
            for item in value.values():
                out.extend(_flatten_text(item))
            return out
        if isinstance(value, list):
            out = []
            for item in value:
                out.extend(_flatten_text(item))
            return out
        return []

    spec_text = " ".join(_flatten_text(specification))
    if len(spec_text) < 200:
        issues.append(
            ReviewIssue(
                severity="high",
                issue_type="unsupported_claim",
                location="specification",
                description="说明书内容过短，可能无法完整支撑全部权利要求。",
                suggestion="请扩展具体实施方式，并逐项对应权利要求核心特征。",
            ).model_dump()
        )
        return issues

    claim_keywords = _find_claim_keywords(claims)
    if not claim_keywords:
        return issues

    missing_keywords = [kw for kw in claim_keywords if kw not in spec_text]
    missing_ratio = len(missing_keywords) / max(len(claim_keywords), 1)
    # Avoid over-sensitive failures: require substantial uncovered features.
    if missing_keywords and missing_ratio >= 0.5:
        issues.append(
            ReviewIssue(
                severity="medium",
                issue_type="unsupported_claim",
                location="claims/specification",
                description=f"疑似缺少支撑的权利要求特征：{', '.join(missing_keywords[:5])}。",
                suggestion="请在说明书中补充上述缺失特征对应的结构、机理或效果描述。",
            ).model_dump()
        )
    return issues


def formality_review(
    *,
    claims: dict[str, Any] | None,
    specification: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Check formal writing risks (absolute terms, punctuation style, simple consistency).
    """
    issues: list[dict[str, Any]] = []
    if not claims and not specification:
        return issues

    abs_terms = ("最优", "唯一", "必须", "绝对", "完全")
    corpus = []
    if claims:
        corpus.append(str(claims))
    if specification:
        corpus.append(str(specification))
    full_text = "\n".join(corpus)

    hit_terms = [term for term in abs_terms if term in full_text]
    if hit_terms:
        issues.append(
            ReviewIssue(
                severity="low",
                issue_type="formality",
                location="claims/specification",
                description=f"检测到绝对化措辞：{', '.join(hit_terms)}。",
                suggestion="建议替换为中性专利撰写措辞，降低不必要的限定风险。",
            ).model_dump()
        )

    # Very lightweight punctuation consistency check.
    if "；" in full_text and ";" in full_text:
        issues.append(
            ReviewIssue(
                severity="low",
                issue_type="inconsistency",
                location="full_document",
                description="检测到疑似混用标点风格。",
                suggestion="请统一全文标点风格，保证格式一致性。",
            ).model_dump()
        )
    return issues


def run_full_review(
    *,
    claims: dict[str, Any] | None,
    specification: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """Aggregate logical and formal review results into one issue list."""
    logic_issues = logic_consistency_review(claims=claims, specification=specification)
    formality_issues = formality_review(claims=claims, specification=specification)
    return logic_issues + formality_issues
