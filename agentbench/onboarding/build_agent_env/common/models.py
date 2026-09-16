"""Small contracts used by individual file builders and their coordinator."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class FileStep:
    """One destination, one stage prompt and one offline validator.

    template is set for fixed files such as .dockerignore. A render callback turns
    schema-constrained model facts into a program-generated file; other model
    steps return file contents. Corrections are bounded per step.
    """

    path: str
    prompt: str
    validate: Callable[[str, "BuildSession"], None]
    template: str | None = None
    response_schema: Path | None = None
    render: Callable[[dict, "BuildSession"], str] | None = None
    request_data: dict = field(default_factory=dict)


@dataclass
class BuildSession:
    source: object
    sdk: object
    settings: object
    environ: object
    context: dict
    answers: str
    attempt: Path
    agent_id: str
    output_fn: Callable[[str], None]
    client_factory: Callable
    client: object = None
    plan: dict = field(default_factory=dict)
    completed: dict[str, str] = field(default_factory=dict)
    current_path: str | None = None
    manifest_options: object = None
    sdk_context: dict = field(default_factory=dict)

    def generate(self, payload: dict, *, prompt: str, schema: dict) -> dict:
        if self.client is None:
            self.client = self.client_factory()
        return self.client.generate(payload, prompt=prompt, schema=schema)

    def payload(self) -> dict:
        from dataclasses import asdict
        from ..build_toml.frameworks import framework_requirements
        from ..build_toml.options import ManifestOptions
        from ..build_toml.tool_routes import network_evidence
        from ..openrouter_provider.privacy import contains_secret
        from .errors import BuildError
        from .layout import build_context
        import json

        options = asdict(self.manifest_options or ManifestOptions())
        if contains_secret(json.dumps(options), self.environ):
            raise BuildError("Deployment options contain credentials; not sent to the model")

        return {"agent_id": self.agent_id, "context": self.context,
                "build_context": build_context(self.source.directory),
                "tool_network_evidence": network_evidence(self.context),
                "framework_requirements": framework_requirements(),
                "deployment_options": options,
                "sdk_requirements": self.sdk.onboarding_requirements(),
                "sdk_context": self.sdk_context,
                "answers": self.answers, "plan": self.plan,
                "completed_files": dict(self.completed)}
