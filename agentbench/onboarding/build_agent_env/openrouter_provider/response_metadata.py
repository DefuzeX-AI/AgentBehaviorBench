"""Extract allowlisted provider metadata without retaining response bodies."""
import json
import re
from .privacy import contains_secret


def response_metadata(response):
    metadata = {}
    choices = response.get("choices") if isinstance(response, dict) else None
    choice = choices[0] if isinstance(choices, list) and choices and isinstance(choices[0], dict) else {}
    finish = choice.get("finish_reason")
    metadata["finish_reason"] = finish if finish in (
        "stop", "length", "content_filter", "tool_calls", "function_call", "error") else "unknown"
    message = choice.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if isinstance(content, str):
        metadata.update(content_chars=len(content), content_bytes=len(content.encode("utf-8", errors="replace")))
    usage = response.get("usage") if isinstance(response, dict) else None
    if isinstance(usage, dict):
        for key in ("prompt_tokens", "completion_tokens", "total_tokens"):
            value = usage.get(key)
            if type(value) is int and 0 <= value <= 10**12:
                metadata[key] = value
        details = usage.get("completion_tokens_details")
        value = details.get("reasoning_tokens") if isinstance(details, dict) else None
        if type(value) is int and 0 <= value <= 10**12:
            metadata["reasoning_tokens"] = value
    return metadata


def content_contains_secret(content, environ):
    if contains_secret(content, environ):
        return True
    # A syntax error elsewhere must not hide a credential encoded in a JSON string.
    unescaped = re.sub(r'\\(?:u[0-9a-fA-F]{4}|["\\/bfnrt])',
                       lambda match: json.loads('"' + match.group() + '"'), content)
    return contains_secret(unescaped, environ)


def decode_location(error):
    return {"json_error": error.msg, "line": error.lineno,
            "column": error.colno, "offset": error.pos}
