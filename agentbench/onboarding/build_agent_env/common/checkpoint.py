"""Persist the plan and completed file hashes for interruption-safe resumption."""

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from .writer import confined, save_json
from .errors import BuildError
from ..build_toml.frameworks import framework_requirements
from ..build_toml.options import ManifestOptions
from ..build_toml.tool_routes import CATALOG


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Checkpoint:
    def __init__(self, session):
        self.path = confined(session.attempt.parent, "build-state.json")
        fingerprint = digest(json.dumps({
            "context": session.context, "answers": session.answers,
            "sdk": session.sdk.onboarding_requirements(),
            "sdk_context": session.sdk_context,
            "framework_requirements": framework_requirements(),
            "manifest_generation": "structured-facts-v1",
            "tool_catalog": digest(CATALOG.read_text()),
            "planning_contract": {
                name: digest((Path(__file__).parents[1] / "planning/assets" / name).read_text())
                for name in ("prompt.md", "response.schema.json")},
            "deployment_options": asdict(session.manifest_options or ManifestOptions()),
        }, sort_keys=True, ensure_ascii=False))
        self.data = {"schema_version": "abb.agent-build.v2", "fingerprint": fingerprint,
                     "plan": None, "files": {}}
        if self.path.exists():
            try:
                saved = json.loads(self.path.read_text())
            except (ValueError, UnicodeError):
                raise BuildError("Unreadable onboarding/build-state.json; review it before resuming") from None
            if not isinstance(saved, dict):
                raise BuildError("onboarding/build-state.json must contain an object")
            if saved.get("schema_version") == self.data["schema_version"] and saved.get("fingerprint") == fingerprint:
                if not isinstance(saved.get("files"), dict):
                    raise BuildError("onboarding/build-state.json contains invalid file records")
                self.data = saved

    def save_plan(self, plan):
        self.data["plan"] = plan
        self.flush()

    def record_file(self, name, content):
        self.data["files"][name] = {"sha256": digest(content), "status": "completed"}
        self.flush()

    def flush(self):
        save_json(self.path, self.data)
