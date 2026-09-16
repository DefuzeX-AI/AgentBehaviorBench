"""Project local schemas onto the conservative Azure/OpenAI output subset.

This is a transport schema, not the authoritative validator. Stage validators
must continue using the original schema, including every omitted constraint.
"""

from copy import deepcopy

from ..common.errors import BuildError

# Azure supports fewer validation keywords than some other OpenRouter providers.
# Keep these constraints in the packaged schemas and enforce them after decoding.
_LOCAL_CONSTRAINTS = frozenset({
    "if", "then", "else",
    "minLength", "maxLength", "pattern", "format",
    "minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum", "multipleOf",
    "minItems", "maxItems", "uniqueItems", "minProperties", "maxProperties",
})
_ANNOTATIONS = frozenset({"$schema", "$comment", "default", "examples"})
_LITERAL_VALUES = frozenset({"type", "enum", "required", "title", "description", "$ref"})


def build_request_schema(schema: dict) -> dict:
    """Return an independent provider schema without changing the local schema.

    Args:
        schema: A stage's full JSON Schema, still used for local validation.
    Returns:
        A copy preserving properties, types, required fields, enums, references,
        closed objects and nested anyOf branches. Unsupported value constraints
        and conditional rules remain local. Unknown constructs fail explicitly
        instead of silently dropping structural requirements.
    """
    return _project(schema)


def _project(schema: dict) -> dict:
    if not isinstance(schema, dict):
        raise BuildError("OpenRouter request schema requires object-form schemas")
    result = {}
    for key, value in schema.items():
        if key in _LOCAL_CONSTRAINTS or key in _ANNOTATIONS:
            continue
        if key in _LITERAL_VALUES:
            # Enum values and property names are data, not schema keywords.
            result[key] = deepcopy(value)
        elif key in {"properties", "$defs"}:
            result[key] = {name: _project(child) for name, child in value.items()}
        elif key == "items":
            result[key] = _project(value)
        elif key == "anyOf":
            result[key] = [_project(child) for child in value]
        elif key == "additionalProperties" and value is False:
            result[key] = False
        elif key == "const":
            # Strict output providers support singleton enums more consistently.
            if "enum" in schema:
                raise BuildError("Use one enum for combined const/enum request constraints")
            result["enum"] = [deepcopy(value)]
        else:
            raise BuildError(f"OpenRouter request schema does not support '{key}'; "
                             "add an explicit projection before using this schema")
    return result
