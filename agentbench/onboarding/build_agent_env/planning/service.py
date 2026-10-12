"""Plan generation is separate from file generation and can be resumed."""

import json
from pathlib import Path

from ..common.errors import BuildPaused
from ..common.repair import RepairBudget, request_response
from ..common.writer import save_json

from ..frameworks.registry import strategy, supported_frameworks

ASSETS = Path(__file__).parent / "assets"


def validate_plan(plan, schema, session):
    selected = strategy(plan.get("framework", "langgraph"))
    contract = json.loads((selected.assets / "planning/response.schema.json").read_text(encoding="utf-8"))
    return selected.validate_plan(plan, contract, session)


def planning_contract():
    """One discovery request, followed by the selected strategy's strict validator."""
    names = supported_frameworks()
    schema = json.loads((ASSETS / "response.schema.json").read_text(encoding="utf-8"))
    for key in ("if", "then", "else"):
        schema.pop(key, None)
    schema["properties"]["framework"] = {"type": "string", "enum": list(names)}
    schema["required"].append("framework")
    prompt = ("Identify the execution framework from supplied source evidence. Set framework "
              "explicitly and apply ONLY its strategy below. Return a plan, not files. "
              "Do not relabel unsupported code to satisfy a strategy.\n\n")
    prompt += "\n\n".join(f"## Strategy: {name}\n" +
        (strategy(name).assets / "planning/prompt.md").read_text(encoding="utf-8") for name in names)
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
    session.output_fn("Plan: analyzing source")
    result = request_response(session, session.payload(), prompt=prompt, schema=schema,
        stage=session.attempt, checkpoint=checkpoint,
        budget=RepairBudget(session.settings.repair_attempts), validator=validate_plan,
        response_prefix="plan-response", validation_prefix="plan-validation")
    save_json(session.attempt / "plan.json", result)
    if result["status"] != "complete":
        raise BuildPaused(result["status"], result["missing_information"])
    checkpoint.save_plan(result)
    return result
