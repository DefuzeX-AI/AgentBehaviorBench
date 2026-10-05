"""Validate schemas locally and delegate requirement rules to the SDK plugin."""
import json
import tempfile
from pathlib import Path
from jsonschema.validators import validator_for
from agentbench.sdk.contracts import SDKOnboardingContext
from ..common.errors import BuildError
from ..common.paths import file_path


def validate_schema(content, session):
    schema = json.loads(content)
    if not isinstance(schema, dict):
        raise BuildError("Input schema must be a JSON object")
    pending = [schema]
    while pending:
        item = pending.pop()
        if isinstance(item, dict):
            reference = item.get("$ref")
            if reference is not None and (not isinstance(reference, str) or not reference.startswith("#")):
                raise BuildError("Input schema references must stay inside the schema")
            pending.extend(item.values())
        elif isinstance(item, list):
            pending.extend(item)
    validator_for(schema).check_schema(schema)


def validate_requirement(content, session):
    with tempfile.TemporaryDirectory(prefix="agent-requirement-check-") as directory:
        root = Path(directory)
        for name, value in {**session.completed, "requirement.md": content}.items():
            path = root / file_path(name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value, encoding="utf-8")
        session.sdk.validate_onboarding(root)
        if isinstance(session.sdk, SDKOnboardingContext):
            session.sdk.validate_onboarding_context(root, context=session.sdk_context)
