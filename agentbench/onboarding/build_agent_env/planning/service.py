"""Plan generation is separate from file generation and can be resumed."""

import json
from pathlib import Path
from jsonschema import Draft202012Validator

from ..common.errors import BuildError, BuildPaused
from ..common.paths import file_path
from ..common.responses import validate_response
from ..common.writer import save_json
from ..openrouter_provider.privacy import contains_secret, redact

ASSETS = Path(__file__).parent / "assets"


def validate_plan(plan, schema, session):
    if isinstance(plan, dict) and "bindings" in plan:
        error = next(Draft202012Validator(schema["properties"]["bindings"]).iter_errors(plan["bindings"]), None)
        if error is not None:
            raise BuildError("Plan bindings must list NEW outer files such as 'bindings/bridge.py', "
                             "not a source entrypoint like 'backend/graph.py:Graph' or a graph node. "
                             "Every complete plan needs an outer binding, including a forwarding "
                             "factory for directly compatible graphs. Explain native symbols in summary.")
        if plan.get("status") == "complete" and not plan["bindings"]:
            raise BuildError("Every complete plan must include an outer binding such as bindings/bridge.py; "
                             "use a forwarding factory when the native graph needs no adaptation")
    validate_response(plan, schema, session)
    bindings = plan["bindings"]
    if len(bindings) != len(set(bindings)) or len(bindings) > session.settings.max_files:
        raise BuildError("Plan contains duplicate bindings or exceeds the file budget")
    if plan["status"] != "complete" and bindings:
        raise BuildError("Incomplete plans must use bindings=[] until the required information is available")
    for name in bindings:
        if not file_path(name).startswith("bindings/"):
            raise BuildError("Plan bindings must be Python files under bindings/")


def prepare_plan(session, checkpoint):
    """Return a source-matched cached plan or request a plan containing no files."""
    schema = json.loads((ASSETS / "response.schema.json").read_text())
    cached = checkpoint.data.get("plan")
    if cached is not None:
        try:
            validate_plan(cached, schema, session)
        except ValueError:
            session.output_fn("Plan: saved analysis no longer satisfies the binding contract; analyzing again")
        else:
            session.output_fn("Plan: reused saved analysis")
            save_json(session.attempt / "plan.json", cached)
            return cached
    payload = session.payload()
    for index in range(session.settings.repair_attempts + 1):
        session.output_fn("Plan: analyzing source" if index == 0 else "Plan: correcting analysis")
        result = session.generate(payload, prompt=(ASSETS / "prompt.md").read_text(), schema=schema)
        if contains_secret(json.dumps(result), session.environ):
            raise BuildError("Model response contains a credential; it was not saved or sent back")
        save_json(session.attempt / f"plan-response-{index + 1}.json", result)
        try:
            validate_plan(result, schema, session)
        except ValueError as exc:
            error = redact(str(exc), session.environ)
            save_json(session.attempt / f"plan-validation-{index + 1}.json", {"error": error})
            if index == session.settings.repair_attempts:
                raise BuildError(error) from None
            payload = {**session.payload(), "previous_response": result, "validation_error": error}
            continue
        save_json(session.attempt / "plan.json", result)
        if result["status"] != "complete":
            raise BuildPaused(result["status"], result["missing_information"])
        checkpoint.save_plan(result)
        return result
    raise AssertionError("unreachable")
