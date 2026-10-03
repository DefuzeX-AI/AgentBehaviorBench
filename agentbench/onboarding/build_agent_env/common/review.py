"""Check source-backed correctness separately from generating a candidate file."""
import json
from pathlib import Path

from .errors import BuildError, BuildPaused
from .responses import validate_response
from .writer import save_json
from ..openrouter_provider.privacy import contains_secret
from ..openrouter_provider.source_requests import generate_with_source

ASSETS = Path(__file__).parent / "assets"


def review_file(step, content, session, stage, prefix, *, checkpoint=None):
    """Return only after a structured review accepts the input/runtime contract."""
    session.output_fn(prefix + ": reviewing source compatibility")
    schema = json.loads((ASSETS / "review.schema.json").read_text(encoding="utf-8"))
    response = generate_with_source(session, {**session.payload(), "response_kind": "configuration_review",
        "target_path": step.path, "proposed_content": content},
        prompt=(ASSETS / "review.md").read_text(encoding="utf-8"), schema=schema,
        stage=stage, checkpoint=checkpoint)
    if contains_secret(json.dumps(response), session.environ):
        raise BuildError("Review response contains a credential; it was not saved or sent back")
    index = 1 + len(list(stage.glob("review-*.json")))
    save_json(stage / f"review-{index}.json", response)
    validate_response(response, schema, session)
    if response["status"] != "complete":
        raise BuildPaused(response["status"], response["missing_information"])
    if response["issues"]:
        raise BuildError("Source compatibility review: " + "; ".join(response["issues"]))
