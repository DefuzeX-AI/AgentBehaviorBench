"""Redact source evidence and reject credentials in model-produced files."""

import re
from collections.abc import Mapping

_SECRET_NAME = re.compile(r"KEY|TOKEN|SECRET|PASSWORD|CREDENTIAL", re.I)
_TOKEN = re.compile(r"\b(?:sk-(?:or-v1-)?[A-Za-z0-9_-]{16,}|gh[pousr]_[A-Za-z0-9]{20,})\b")
_ASSIGNMENT = re.compile(
    r"(?im)^([^\n=:\s]*(?:api_key|token|secret|password)[^\n=:\s]*\s*[:=]\s*)([^\n]+)$"
)


def redact(text: str, environ: Mapping[str, str]) -> str:
    """Remove known secret values and recognizable tokens; preserve variable names."""
    for key, value in sorted(environ.items(), key=lambda item: len(item[1]), reverse=True):
        if _SECRET_NAME.search(key) and len(value) >= 8:
            text = text.replace(value, "[REDACTED]")
    text = _TOKEN.sub("[REDACTED]", text)
    return _ASSIGNMENT.sub(r"\1[REDACTED]", text)


def contains_secret(text: str, environ: Mapping[str, str]) -> bool:
    """Reject copied runtime secrets and token-shaped values in generated files."""
    return bool(_TOKEN.search(text)) or any(
        _SECRET_NAME.search(key) and len(value) >= 8 and value in text
        for key, value in environ.items()
    )
