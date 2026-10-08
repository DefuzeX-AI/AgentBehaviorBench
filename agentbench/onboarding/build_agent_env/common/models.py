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
    review_data: dict = field(default_factory=dict)


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
    generation_model: str | None = None

    def generate(self, payload: dict, *, prompt: str, schema: dict) -> dict:
        if self.client is None:
            self.client = self.client_factory()
        return self.client.generate(payload, prompt=prompt, schema=schema)

    def payload(self) -> dict:
        from agentbench.sdk.contracts import SDKOnboardingInputs
        from dataclasses import asdict
        from ..build_toml.frameworks import framework_requirements
        from ..frameworks.registry import strategy
        from ..build_toml.options import ManifestOptions
        from ..build_toml.tool_routes import network_evidence
        from ..openrouter_provider.privacy import contains_secret
        from ..openrouter_provider.context import environment_presence
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
                "framework_documents": strategy(self.plan["framework"]).reference_documents()
                    if self.plan.get("framework") else {},
                "deployment_options": options,
                "native_environment_presence": environment_presence(self.context, self.environ),
                "native_default_policy": "Preserve upstream optional defaults unless explicitly overridden. Do not force human approval or --no-interrupt just to finish a benchmark. Unset optional model endpoint variables use the native default endpoint; do not ask whether to override them.",
                "sdk_requirements": self.sdk.onboarding_requirements(),
                "sdk_input_types": list(self.sdk.onboarding_input_types())
                    if isinstance(self.sdk, SDKOnboardingInputs) else [],
                "sdk_context": self.sdk_context,
                "answers": self.answers, "plan": self.plan,
                "completed_files": dict(self.completed)}
