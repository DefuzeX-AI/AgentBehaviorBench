"""Plan generation is separate from file generation and can be resumed."""

import json
from pathlib import Path

from ..common.errors import BuildError, BuildPaused
from ..common.writer import save_json
from ..openrouter_provider.privacy import contains_secret, redact

from ..frameworks.registry import strategy, supported_frameworks

ASSETS = Path(__file__).parent / "assets"


def validate_plan(plan, schema, session):
    selected = strategy(plan.get("framework", "langgraph"))
    contract = json.loads((selected.assets / "planning/response.schema.json").read_text())
    return selected.validate_plan(plan, contract, session)


def planning_contract():
    """One discovery request, followed by the selected strategy's strict validator."""
    names = supported_frameworks()
    schema = json.loads((ASSETS / "response.schema.json").read_text())
    for key in ("if", "then", "else"):
        schema.pop(key, None)
    schema["properties"]["framework"] = {"type": "string", "enum": list(names)}
    schema["required"].append("framework")
    prompt = ("Identify the execution framework from supplied source evidence. Set framework "
              "explicitly and apply ONLY its strategy below. Return a plan, not files. "
              "Do not relabel unsupported code to satisfy a strategy.\n\n")
    prompt += "\n\n".join(f"## Strategy: {name}\n" +
        (strategy(name).assets / "planning/prompt.md").read_text() for name in names)
    return schema, prompt


def prepare_plan(session, checkpoint):
    """Return a source-matched cached plan or request a plan containing no files."""
    schema, prompt = planning_contract()
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
        result = session.generate(payload, prompt=prompt, schema=schema)
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
