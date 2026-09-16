"""Compact identities for human-facing benchmark progress."""

from __future__ import annotations


def case_identity(agent_id: object, case_index: object = None, job_id: object = None) -> str:
    """Identify a concurrent Case without repeating artifact IDs on every line."""
    parts = [str(agent_id or "agent")]
    if type(case_index) is int:
        parts.append(f"case {case_index + 1}")
    elif job_id:
        parts.append(f"job {short_id(job_id)}")
    return f"[{' · '.join(parts)}]"


def short_id(value: object, length: int = 8) -> str:
    """Keep a small correlation hint; full IDs remain in saved trace artifacts."""
    text = str(value)
    return text[-length:] if len(text) > length else text
