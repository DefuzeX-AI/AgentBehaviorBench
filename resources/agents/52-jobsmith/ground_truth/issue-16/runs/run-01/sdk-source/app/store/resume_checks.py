"""Persisted resume health-check reports."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from app.store import db


def _label(label: str, profile: dict | None, resume_label: str) -> str:
    candidate = ((profile or {}).get("name") or "").strip()
    if label.strip():
        return label.strip()[:200]
    if candidate:
        return f"{candidate} 履歷健檢"
    if resume_label.strip():
        return f"{resume_label.strip()} 履歷健檢"
    return "未命名履歷健檢"


def save_check(
    label: str,
    resume_label: str,
    profile: dict | None,
    assessment: dict,
) -> int:
    mode = str(assessment.get("assessment_mode") or "deep")
    reason = str(assessment.get("fallback_reason") or "")
    candidate = str((profile or {}).get("name") or "")
    conn = db.get_conn()
    with db.LOCK:
        cur = conn.execute(
            "INSERT INTO resume_checks("
            "created_at,label,resume_label,candidate_name,overall_score,assessment_mode,"
            "fallback_reason,profile_json,assessment_json) VALUES(?,?,?,?,?,?,?,?,?)",
            (
                datetime.now(timezone.utc).isoformat(),
                _label(label, profile, resume_label),
                (resume_label or "")[:200],
                candidate[:120],
                int(assessment.get("overall_score") or 0),
                mode,
                reason[:500],
                json.dumps(profile, ensure_ascii=False) if profile else None,
                json.dumps(assessment, ensure_ascii=False),
            ),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_checks() -> list[dict]:
    conn = db.get_conn()
    with db.LOCK:
        rows = conn.execute(
            "SELECT id,created_at,label,resume_label,candidate_name,overall_score,"
            "assessment_mode,fallback_reason FROM resume_checks ORDER BY id DESC"
        ).fetchall()
    return [dict(r) for r in rows]


def get_check(cid: int) -> dict | None:
    conn = db.get_conn()
    with db.LOCK:
        row = conn.execute("SELECT * FROM resume_checks WHERE id=?", (cid,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["profile"] = json.loads(data.pop("profile_json") or "null")
    data["assessment"] = json.loads(data.pop("assessment_json") or "{}")
    return data


def delete_check(cid: int) -> None:
    conn = db.get_conn()
    with db.LOCK:
        conn.execute("DELETE FROM resume_checks WHERE id=?", (cid,))
        conn.commit()


def delete_all_checks() -> None:
    conn = db.get_conn()
    with db.LOCK:
        conn.execute("DELETE FROM resume_checks")
        conn.commit()
