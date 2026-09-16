"""Bounded, redacted diagnostics from OpenRouter's public error fields."""

import json
import re
from http.client import HTTPException

from .privacy import redact

_BODY_LIMIT = 65536
_DISPLAY_LIMIT = 1600
_ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")
_AUTH = re.compile(r"(?i)\b(Bearer|Basic)\s+[A-Za-z0-9._~+/=-]+")
_USERINFO = re.compile(r"(?i)(https?://)[^\s/]+@")
_SECRET_ASSIGNMENT = re.compile(
    r'''(?ix)(\b(?:authorization|cookie|set-cookie|[\w-]*(?:api[_-]?key|token|secret|password|credential)[\w-]*)
        ["']?\s*[:=]\s*)(?:"[^"]*"|'[^']*'|[^\s,;&}\]]+)'''
)


def describe_http_error(error, *, environ, api_key, max_bytes):
    """Return HTTP status plus allowed error fields; never dump a response body.

    Read at most the configured response budget, capped at 64 KiB. OpenRouter
    may wrap a provider JSON error in metadata.raw; extract its message/type/param
    instead of exposing request echoes, headers or arbitrary metadata. Redaction
    precedes single-line display truncation so partial secrets are not printed.
    The caller owns closing the HTTPError and retains its existing retry policy.
    """
    prefix = f"OpenRouter HTTP {error.code}"
    limit = min(max_bytes, _BODY_LIMIT)
    try:
        raw = error.read(limit + 1)
        if len(raw) > limit:
            return prefix + " (error details exceeded the read limit)"
        body = json.loads(raw)
    except (OSError, ValueError, TypeError, RecursionError, HTTPException):
        return prefix
    if not isinstance(body, dict):
        return prefix
    value = body.get("error", body)
    details = _fields(value)
    metadata = value.get("metadata") if isinstance(value, dict) else None
    if isinstance(metadata, dict):
        provider = metadata.get("provider_name")
        if isinstance(provider, str):
            details.append("provider=" + provider)
        upstream = metadata.get("raw")
        if isinstance(upstream, str):
            try:
                upstream = json.loads(upstream)
            except (ValueError, RecursionError):
                upstream = None
        if isinstance(upstream, dict):
            details.extend(_fields(upstream.get("error", upstream)))
    text = "; ".join(dict.fromkeys(details))
    text = _ANSI.sub("", text)
    text = redact(text, environ).replace(api_key, "[REDACTED]")
    text = _AUTH.sub(r"\1 [REDACTED]", text)
    text = _USERINFO.sub(r"\1[REDACTED]@", text)
    text = _SECRET_ASSIGNMENT.sub(r"\1[REDACTED]", text)
    text = " ".join("".join(character if character.isprintable() else " " for character in text).split())
    if len(text) > _DISPLAY_LIMIT:
        text = text[:_DISPLAY_LIMIT] + " … [truncated]"
    return prefix + (": " + text if text else "")


def _fields(value):
    if not isinstance(value, dict):
        return []
    result = []
    message = value.get("message")
    if isinstance(message, str) and message.strip():
        result.append(message)
    for key in ("code", "type", "param"):
        item = value.get(key)
        if type(item) in (str, int) and str(item):
            result.append(f"{key}={item}")
    return result
