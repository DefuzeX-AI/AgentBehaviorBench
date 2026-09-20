"""LangGraph plan validation without importing upstream code."""
from jsonschema import Draft202012Validator
from ...common.errors import BuildError
from ...common.paths import file_path
from ...common.responses import validate_response

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

