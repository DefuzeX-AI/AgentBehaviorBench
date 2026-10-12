"""Bounded schema diagnostics built from validator facts, never instance dumps."""
import json
from itertools import islice
from jsonschema import Draft202012Validator
from ..openrouter_provider.privacy import redact

MAX_ERRORS = 5
MAX_DIAGNOSTIC_CHARS = 2048


def json_type(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, str):
        return "string"
    return "number"


def _leaves(error):
    if not error.context:
        yield error
        return
    # Prefer errors inside a structurally matching branch over e.g. "object is not null".
    nested = [child for child in error.context if
              not (child.validator == "type" and child.absolute_path == error.absolute_path)]
    for child in (nested or error.context):
        yield from _leaves(child)


def _path(parts):
    return "$" + "".join(f"[{p}]" if isinstance(p, int) else
                         "." + p if p.isidentifier() else "[" + json.dumps(p) + "]"
                         for p in parts)


def schema_diagnostics(response, schema, environ):
    errors = []
    for parent in islice(Draft202012Validator(schema).iter_errors(response), 50):
        for error in islice(_leaves(parent), 50):
            path, rule = list(error.absolute_path), error.validator
            expected = error.validator_value
            if rule == "required" and isinstance(error.instance, dict):
                for name in expected:
                    if name not in error.instance:
                        errors.append((_path([*path, name]), "required property is missing"))
            elif rule == "type":
                errors.append((_path(path), f"expected {expected}, got {json_type(error.instance)}"))
            elif rule in ("enum", "const", "pattern"):
                # Allowed values come from the stage schema. Do not echo the actual value.
                errors.append((_path(path), f"expected {rule} {json.dumps(expected)}, got {json_type(error.instance)}"))
            elif rule in ("minLength", "maxLength", "minItems", "maxItems", "minimum",
                          "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf"):
                errors.append((_path(path), f"expected {rule}={expected}; got {json_type(error.instance)}"))
            elif rule == "additionalProperties":
                errors.append((_path(path), "unexpected properties are not allowed"))
            else:
                errors.append((_path(path), f"failed {rule} constraint"))
    if not errors:
        return None
    lines = sorted(set((redact(path, environ)[:256], redact(message, environ)[:256])
                       for path, message in errors))
    text = "Model response schema mismatch:\n" + "\n".join(
        f"{path}: {message}" for path, message in lines[:MAX_ERRORS])
    if len(lines) > MAX_ERRORS:
        text += "\nAdditional schema errors omitted."
    return text[:MAX_DIAGNOSTIC_CHARS]
