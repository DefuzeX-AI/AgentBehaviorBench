"""Check source-backed correctness separately from generating a candidate file."""
import json
from pathlib import Path

from .errors import BuildError, BuildPaused
from .repair import RepairBudget, request_response

ASSETS = Path(__file__).parent / "assets"


def review_file(step, content, session, stage, prefix, *, checkpoint=None, budget=None):
    """Return only after a structured review accepts the input/runtime contract."""
    session.output_fn(prefix + ": reviewing source compatibility")
    schema = json.loads((ASSETS / "review.schema.json").read_text(encoding="utf-8"))
    response = request_response(session, {**session.payload(), "response_kind": "configuration_review",
        "target_path": step.path, "proposed_content": content},
        prompt=(ASSETS / "review.md").read_text(encoding="utf-8"), schema=schema,
        stage=stage, checkpoint=checkpoint,
        budget=budget if budget is not None else RepairBudget(session.settings.repair_attempts),
        response_prefix="review", validation_prefix="review-validation", secret_label="Review")
    if response["status"] != "complete":
        raise BuildPaused(response["status"], response["missing_information"])
    if response["issues"]:
        raise BuildError("Source compatibility review: " + "; ".join(response["issues"]))
