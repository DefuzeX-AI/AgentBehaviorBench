"""Expand selected wire protocols into explicit credentials and model routes."""

from copy import deepcopy
import json
from pathlib import Path

from ..common.errors import BuildError


def protocol_catalog():
    return json.loads((Path(__file__).parent / "assets/protocols.json").read_text())


def interception_for(models, tool_routes):
    """Expand catalog choices; tool routes remain explicit evidence-based scopes."""
    if not models:
        if tool_routes:
            raise BuildError("Tool-only interception is not supported by the current runtime configuration")
        return None
    catalog, credentials, routes = protocol_catalog(), {}, []
    for model in models:
        protocol, env = model["protocol"], model["agent_env"]
        if protocol not in catalog:
            raise BuildError(f"No onboarding protocol template for {protocol!r}; do not substitute a different protocol")
        entry = catalog[protocol]
        credential_id = entry["credential_id"]
        if env != entry["agent_env"]:
            credential_id += "-" + env.lower().replace("_", "-")
        credential = {"id": credential_id, "agent_env": env, "auth_plugin": entry["auth_plugin"]}
        if credential_id in credentials and credentials[credential_id] != credential:
            raise BuildError("Model credential definitions conflict")
        credentials[credential_id] = credential
        endpoint = model["endpoint"]
        scope = deepcopy(endpoint if endpoint is not None else {
            key: entry[key] for key in ("host_patterns", "ports", "methods", "path_patterns")})
        route = {"id": protocol, **scope, "protocol_plugin": protocol, "credential": credential_id}
        if any({k: v for k, v in old.items() if k != "id"} ==
               {k: v for k, v in route.items() if k != "id"} for old in routes):
            continue
        suffix = sum(item["protocol_plugin"] == protocol for item in routes)
        if suffix:
            route["id"] += f"-{suffix + 1}"
        routes.append(route)
    return {"required": True, "trust_plugin": "pem-env", "credentials": list(credentials.values()),
            "routes": routes, "tool_routes": deepcopy(tool_routes)}
