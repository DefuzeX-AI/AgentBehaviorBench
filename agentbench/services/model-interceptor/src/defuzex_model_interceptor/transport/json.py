"""Shared JSON request and byte serialization helpers."""
import json


def json_bytes(value, *, ascii_only=False):
    return json.dumps(value, ensure_ascii=ascii_only, separators=(",", ":")).encode("utf-8")


def json_request(request):
    payload = json.loads(request.content or b"{}")
    if not isinstance(payload, dict):
        raise ValueError("Model request body must be an object")
    return payload
