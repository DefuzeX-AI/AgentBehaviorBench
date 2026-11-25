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
        A copy preserving properties, enums, references, closed objects and
        nested anyOf branches. Optional fields use required nullable wire slots;
        restore_optional_fields removes wire-only nulls after decoding.
        Unsupported value constraints
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
    if "properties" in result:
        required = set(result.get("required", []))
        for name, child in result["properties"].items():
            if name not in required:
                # Strict providers require every property. Null represents an
                # omitted optional field only on the wire; restore it below.
                result["properties"][name] = {"anyOf": [child, {"type": "null"}]}
        result["required"] = list(result["properties"])
    return result


def restore_optional_fields(value, schema: dict, *, root=None):
    """Decode wire-only null placeholders before authoritative local validation.

    Required fields and fields whose local schema accepts null are untouched.
    Invalid values remain invalid; this is not a repair or validation bypass.
    """
    from jsonschema import Draft202012Validator

    root = schema if root is None else root
    if "$ref" in schema:
        reference = schema["$ref"]
        if not reference.startswith("#/"):
            raise BuildError("Optional field restoration requires local schema references")
        target = root
        for part in reference[2:].split("/"):
            target = target[part.replace("~1", "/").replace("~0", "~")]
        return restore_optional_fields(value, target, root=root)
    if "anyOf" in schema:
        for branch in schema["anyOf"]:
            projected = build_request_schema(branch)
            if "$defs" in root:
                projected.setdefault("$defs", build_request_schema(root)["$defs"])
            if Draft202012Validator(projected).is_valid(value):
                return restore_optional_fields(value, branch, root=root)
        return value
    if isinstance(value, dict) and "properties" in schema:
        restored = dict(value)
        for name, child in schema["properties"].items():
            if name not in value:
                continue
            nullable_schema = {**child, "$defs": root.get("$defs", {})}
            if (value[name] is None and name not in schema.get("required", [])
                    and not Draft202012Validator(nullable_schema).is_valid(None)):
                del restored[name]
            else:
                restored[name] = restore_optional_fields(value[name], child, root=root)
        return restored
    if isinstance(value, list) and "items" in schema:
        return [restore_optional_fields(item, schema["items"], root=root) for item in value]
    return value
