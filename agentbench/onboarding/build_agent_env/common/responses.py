"""Validate provider JSON and source evidence without installing any files."""

import json
from jsonschema import Draft202012Validator

from ..openrouter_provider.privacy import contains_secret
from .errors import BuildError


def validate_response(response, schema, session):
    if contains_secret(json.dumps(response), session.environ):
        raise BuildError("Model response contains a credential; it was not saved or sent back")
    if next(Draft202012Validator(schema).iter_errors(response), None) is not None:
        raise BuildError("Model response does not match this stage's response schema")
    available = {item["path"] for item in session.context["files"]}
    if not response["evidence"] or any(name not in available for name in response["evidence"]):
        raise BuildError("Model response cites missing source evidence")
    if response["status"] == "complete" and response["missing_information"]:
        raise BuildError("Complete response still has unresolved questions")
    if response["status"] != "complete" and not response["missing_information"]:
        raise BuildError("Incomplete response must explain what is missing or unsupported")
