"""Prepare the optional schema before generating the SDK requirement document."""
from pathlib import Path
from ..common.models import FileStep
from .validation import validate_schema, validate_requirement

ASSETS = Path(__file__).parent / "assets"


def steps(plan):
    result = []
    if plan["needs_input_schema"]:
        result.append(FileStep("evaluation/input-schema.json", (ASSETS / "schema.md").read_text(), validate_schema))
    result.append(FileStep("requirement.md", (ASSETS / "requirement.md").read_text(), validate_requirement))
    return result
