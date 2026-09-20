"""Assemble a manifest from bounded facts plus program/user-owned policy."""

from copy import deepcopy
import json

from jsonschema import Draft202012Validator

from .encoding import encode_manifest
from .environment import runtime_environment
from ..frameworks.registry import strategy
from .options import ManifestOptions
from .protocols import interception_for
from .provenance import source_metadata
from ..common.errors import BuildError

SCHEMA = strategy("langgraph").manifest_schema


def render_manifest(facts, *, source, agent_id, options=None):
    """Return TOML without writing any file or invoking an Agent/model.

    facts contains source-derived names, adapter inputs, model protocol choices
    and explicit tool routes. Identity/provenance, runtime/build/launch policy and
    replay safety are program-owned. Optional context comes only from the caller.
    Existing Agent files are never changed by this function.
    """
    selected = strategy(facts.get("framework"))
    schema = json.loads(selected.manifest_schema.read_text())["properties"]["facts"]["anyOf"][0]
    error = next(Draft202012Validator(schema).iter_errors(facts), None)
    if error:
        raise BuildError(f"Invalid manifest facts at {error.json_path}: {error.message}")
    options = options or ManifestOptions()
    adapter = selected.render_adapter(facts["adapter"])
    if options.adapter_context:
        adapter["context"] = deepcopy(options.adapter_context)
    manifest = {
        "schema_version": "defuzex-bench.agent.v2", "agent_id": agent_id,
        "display_name": facts["display_name"], "framework": facts["framework"],
        "evaluation": {"replay_safe": False}, "source": source_metadata(source),
        "runtime": {"type": "docker", "execution": "oneshot", "timeout_sec": options.timeout_sec},
        "build": {"context": ".", "dockerfile": "Dockerfile"},
        "launch": {"argv": ["python", "-m", "agentbench.runtime.agentcontainer.worker"],
                   "workdir": "/opt/agent"}, "adapter": adapter,
    }
    interception = interception_for(facts["models"], facts["tool_routes"])
    manifest["runtime"].update(runtime_environment(facts["env_keys"], facts["secret_env_keys"], interception))
    if options.observe:
        fields = facts["input_fields"]
        if len({item["name"] for item in fields}) != len(fields):
            raise BuildError("Input field names must be unique")
        # The current observe form reads strings only. Use its existing JSON
        # fallback for mixed/nested inputs instead of coercing numbers to text.
        manifest["observe"] = {"input_fields": [
            {"name": item["name"], "label": item["name"], "required": item["required"]}
            for item in fields] if all(item["type"] == "string" for item in fields) else []}
    if interception is not None:
        manifest["llm_interception"] = interception
    return encode_manifest(manifest)
