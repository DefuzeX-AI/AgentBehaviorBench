"""Persist public SDK error data separately from bounded display summaries."""
from collections.abc import Mapping
import math

from agentbench.observe.store import environment_secrets, redact


MAX_ERROR_BYTES = 256 * 1024
MAX_ERROR_ITEMS = 4096
MAX_ERROR_DEPTH = 16


def error_snapshot(value, *, environ=None):
    """Keep JSON data, redact credentials, and explicitly mark diagnostic omissions.

    Never serialize transport objects or use their repr as diagnostic content.
    The bounded tree fits comfortably inside the host diagnostic file limit.
    """
    remaining = MAX_ERROR_BYTES
    items = MAX_ERROR_ITEMS
    active = set()
    omissions = []

    def omit(path, reason):
        if len(omissions) < 32:
            omissions.append({'path': path[:240], 'reason': reason})
        return {'abb_diagnostic_omission': reason}

    def walk(item, path, depth):
        nonlocal remaining, items
        items -= 1
        if items < 0 or remaining <= 0:
            return omit(path, 'size_limit')
        if depth > MAX_ERROR_DEPTH:
            return omit(path, 'depth_limit')
        if item is None or isinstance(item, (bool, int)):
            remaining -= len(str(item)) + 2
            return item
        if isinstance(item, float):
            remaining -= 32
            return item if math.isfinite(item) else omit(path, 'non_json_number')
        if isinstance(item, str):
            # Escaping can expand each byte by six in the JSON document.
            limit = max(0, remaining // 6 - 32)
            raw = item.encode('utf-8', errors='replace')
            if len(raw) > limit:
                item = raw[:limit].decode('utf-8', errors='ignore') + ' [ABB truncated]'
                omit(path, 'size_limit')
            remaining -= 6 * len(item.encode('utf-8')) + 2
            return item
        if not isinstance(item, (Mapping, list, tuple)):
            return omit(path, 'non_json_value')
        identifier = id(item)
        if identifier in active:
            return omit(path, 'cycle')
        active.add(identifier)
        remaining -= 2
        try:
            if isinstance(item, Mapping):
                result = {}
                for key, child in item.items():
                    if items <= 0 or remaining <= 0:
                        omit(path, 'size_limit')
                        break
                    if not isinstance(key, (str, int, float, bool)):
                        omit(path, 'non_json_key')
                        continue
                    key = str(key)
                    if len(key.encode('utf-8')) * 6 + 4 > remaining:
                        omit(path, 'size_limit')
                        break
                    remaining -= len(key.encode('utf-8')) * 6 + 4
                    result[key] = walk(child, path + '/' + key, depth + 1)
                return result
            result = []
            for index, child in enumerate(item):
                if items <= 0 or remaining <= 0:
                    omit(path, 'size_limit')
                    break
                remaining -= 1
                result.append(walk(child, path + '/' + str(index), depth + 1))
            return result
        finally:
            active.remove(identifier)

    result = walk(value, '', 0)
    if omissions and isinstance(result, dict):
        result['abb_diagnostic_omissions'] = omissions
    return redact(result, environment_secrets(environ))


def exception_record(error, *, phase=None, input_id=None):
    """Capture public attributes, including future SDK fields, without private state."""
    value = {'type': type(error).__name__,
             **{key: getattr(error, key, None) for key in
                ('code', 'retryable', 'client_request_id', 'request_id')}}
    if phase is not None:
        value['phase'] = phase
    if input_id is not None:
        value['input_id'] = input_id
    value['message'] = str(error)
    value.update({key: item for key, item in vars(error).items()
                  if not key.startswith('_') and key not in value})
    return error_snapshot(value)
