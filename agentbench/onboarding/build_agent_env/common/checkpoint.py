"""Persist the plan and completed file hashes for interruption-safe resumption."""

import hashlib
import json
from pathlib import Path
from dataclasses import asdict

from .writer import confined, save_json
from .errors import BuildError
from agentbench.sdk.contracts import SDKOnboardingInputs
from ..frameworks.registry import framework_requirements, STRATEGIES
from ..build_toml.options import ManifestOptions
from ..build_toml.tool_routes import CATALOG
from ..openrouter_provider.source_requests import add_source_files
from ..openrouter_provider.context import environment_presence


def digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


class Checkpoint:
    def __init__(self, session):
        self.path = confined(session.attempt.parent, "build-state.json")
        self.session = session
        saved = None
        requested = []
        identity = [session.source.repository, session.source.revision]
        if self.path.exists():
            try:
                if self.path.stat().st_size > session.settings.max_response_bytes:
                    raise ValueError('Oversized build state')
                saved = json.loads(self.path.read_text(encoding="utf-8"))
            except (ValueError, UnicodeError):
                raise BuildError("Unreadable onboarding/build-state.json; review it before resuming") from None
            if not isinstance(saved, dict):
                raise BuildError("onboarding/build-state.json must contain an object")
            if saved.get('source_identity') == identity:
                paths = saved.get('requested_source_files', [])
                if not isinstance(paths, list) or len(paths) > session.settings.max_files or any(not isinstance(name, str) for name in paths):
                    raise BuildError('Invalid requested source files in build state')
                add_source_files(session, paths)
                requested = paths
        fingerprint = self.fingerprint()
        self.data = {"schema_version": "abb.agent-build.v2", "fingerprint": fingerprint,
                     "plan": None, "files": {}, 'source_identity': identity,
                     'requested_source_files': requested}
        if saved is not None and saved.get("schema_version") == self.data["schema_version"] and saved.get("fingerprint") == fingerprint:
            if not isinstance(saved.get("files"), dict) or not isinstance(saved.get('reviews', {}), dict):
                raise BuildError("onboarding/build-state.json contains invalid file records")
            self.data = saved

    def fingerprint(self):
        session = self.session
        fingerprint = digest(json.dumps({
            "context": session.context, "answers": session.answers,
            "generation_model": session.generation_model,
            "native_environment_presence": environment_presence(session.context, session.environ),
            "source_request_contract": "bounded-existing-files-v1",
            "sdk": session.sdk.onboarding_requirements(),
            "sdk_input_types": session.sdk.onboarding_input_types()
                if isinstance(session.sdk, SDKOnboardingInputs) else (),
            "sdk_context": session.sdk_context,
            "framework_requirements": framework_requirements(),
            "framework_documents": {name: {title: digest(content)
                for title, content in item.reference_documents().items()}
                for name, item in STRATEGIES.items()},
            "manifest_generation": "framework-strategies-v2",
            "semantic_review": {path.name: digest(path.read_text(encoding="utf-8"))
                for path in sorted((Path(__file__).parent / "assets").glob("review.*"))},
            "planning_dispatch": digest((Path(__file__).parents[1] / "planning/assets/response.schema.json").read_text(encoding="utf-8")),
            "tool_catalog": digest(CATALOG.read_text(encoding="utf-8")),
            "planning_contract": {name: {"version": item.version, "assets": {
                str(path.relative_to(item.assets)): digest(path.read_text(encoding="utf-8"))
                for path in sorted(item.assets.rglob("*")) if path.is_file()}}
                for name, item in STRATEGIES.items()},
            "deployment_options": asdict(session.manifest_options or ManifestOptions()),
        }, sort_keys=True, ensure_ascii=False))
        return fingerprint

    def record_sources(self, paths):
        self.data['requested_source_files'] = list(dict.fromkeys([*self.data.get('requested_source_files', []), *paths]))
        self.data['fingerprint'] = self.fingerprint()
        self.flush()

    def save_plan(self, plan):
        self.data["plan"] = plan
        self.flush()

    def record_file(self, name, content):
        self.data["files"][name] = {"sha256": digest(content), "status": "completed"}
        self.flush()

    def record_review(self, name, content):
        self.data.setdefault("reviews", {})[name] = digest(content)
        self.flush()

    def flush(self):
        save_json(self.path, self.data)
