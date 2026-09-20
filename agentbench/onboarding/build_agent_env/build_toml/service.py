"""The agent.toml stage declares interfaces used by subsequent builders."""
from pathlib import Path
from ..common.models import FileStep
from .validation import validate_manifest
from .rendering import render_manifest
from ..frameworks.registry import strategy
from .protocols import protocol_catalog
from .tool_routes import network_evidence, complete_routes


def render_response(response, session):
    facts = {**response["facts"], "tool_routes": complete_routes(response["facts"]["tool_routes"],
                                                              network_evidence(session.context))}
    adapter = dict(facts["adapter"])
    filename, separator, symbol = (adapter.get("binding") or "").rpartition(":")
    if separator and filename in session.plan.get("bindings", []) and filename.startswith("bindings/"):
        adapter["binding"] = filename.removeprefix("bindings/") + ":" + symbol
    facts["adapter"] = adapter
    return render_manifest(facts, source=session.source, agent_id=session.agent_id,
                           options=session.manifest_options)


def step(framework="langgraph"):
    assets = Path(__file__).parent / "assets"
    selected = strategy(framework)
    prompt = (selected.assets / "manifest/prompt.md").read_text() + "\n\n" + (assets / "client-transports.md").read_text()
    return FileStep("agent.toml", prompt,
                    validate_manifest, response_schema=selected.manifest_schema, render=render_response,
                    request_data={"response_kind": "configuration_facts",
                                  "protocol_catalog": protocol_catalog()})
