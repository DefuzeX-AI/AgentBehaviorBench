"""Coordinate a resumable plan and sequential file builders; never certify here."""

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from agentbench.harness.session.locking import SuiteLock
from agentbench.onboarding.source import DownloadedAgent
from agentbench.sdk.contracts import SDKOnboarding

from .build_blinding.service import steps as binding_steps
from .build_dockerfile.service import steps as docker_steps
from .build_requirement.service import steps as requirement_steps
from .build_toml.service import step as manifest_step
from .common.checkpoint import Checkpoint
from .common.errors import BuildError, BuildPaused
from .common.generation import run_step
from .common.models import BuildSession
from .common.registry import register_agent
from .common.records import records_directory
from .common.sdk_context import load_sdk_context
from .common.validation import validate_unit
from .common.writer import confined, save_json, start_attempt
from .openrouter_provider.client import OpenRouterClient
from .openrouter_provider.context import collect_context
from .openrouter_provider.privacy import redact
from .openrouter_provider.settings import load_settings
from .planning.service import prepare_plan


@dataclass(frozen=True)
class BuildResult:
    status: str
    attempt: Path
    agent_id: str
    messages: tuple[str, ...] = ()


def build_agent_environment(
    source: DownloadedAgent, *, sdk: SDKOnboarding, registry_path: Path,
    environ: Mapping[str, str], settings_path: Path | None = None,
    model: str | None = None, answers_path: Path | None = None, client=None,
    output_fn=print,
    manifest_options=None,
) -> BuildResult:
    """Generate, validate and save each integration file before requesting the next.

    Args:
        source: Downloaded unit; upstream source is never modified or imported.
        sdk: Plugin owning the evaluation-document requirements and validation.
        registry_path: Registry updated only after all files pass final validation.
        environ: Host model configuration and secret values used for redaction.
        settings_path: Optional TOML request budgets and per-stage repair limits.
        model: Explicit generation model, separate from the Agent's runtime model.
        answers_path: Optional UTF-8 answers to an earlier plan/stage's questions.
        client: Optional injectable structured-response client for offline testing.
        output_fn: Progress callback; reports each file immediately after saving.
        manifest_options: Explicit timeout, Observe and adapter-context choices;
            defaults to 300 seconds, no Observe form and no context override.
    Returns:
        A completed or paused BuildResult. Previously saved files survive errors
        and interruption; reruns reuse a source-matched plan and valid files.
    """
    if not isinstance(sdk, SDKOnboarding):
        raise BuildError("Selected SDK has no onboarding requirements and validation")
    settings = load_settings(settings_path)
    if not source.directory.resolve().is_relative_to(registry_path.resolve().parent.parent):
        raise BuildError("Agent directory must be inside the --registry repository root")
    answers = ""
    if answers_path is not None:
        if answers_path.stat().st_size > settings.max_file_bytes:
            raise BuildError("Answers file exceeds max_file_bytes")
        answers = redact(answers_path.read_text(encoding="utf-8"), environ)
    records = records_directory(source.directory, registry_path)
    lock = SuiteLock(records)
    lock.acquire()
    try:
        attempt = start_attempt(records)
        session = BuildSession(source=source, sdk=sdk, settings=settings, environ=environ,
            context=collect_context(source, settings, environ), answers=answers, attempt=attempt,
            agent_id=source.directory.name.split("-", 1)[1], output_fn=output_fn,
            client=client, client_factory=lambda: OpenRouterClient(settings, environ, model=model),
            manifest_options=manifest_options)
        return _build(session, registry_path)
    finally:
        lock.close()


def _build(session, registry_path):
    context = session.context
    save_json(session.attempt / "context.json", {
        **{key: value for key, value in context.items() if key != "files"},
        "files": [{"path": item["path"], "truncated": item["truncated"]} for item in context["files"]]})
    try:
        session.sdk_context = load_sdk_context(session)
        checkpoint = Checkpoint(session)
        session.plan = prepare_plan(session, checkpoint)
        steps = [manifest_step(session.plan.get("framework", "langgraph")), *binding_steps(session.plan), *docker_steps(),
                 *requirement_steps(session.plan)]
        for index, step in enumerate(steps, 1):
            run_step(step, session, checkpoint, index, len(steps))
        validate_unit(session.source.directory, session.sdk, expected_id=session.agent_id,
                      sdk_context=session.sdk_context)
        register_agent(session.source.directory, registry_path, session.source.repository)
        result = BuildResult("generated", session.attempt, session.agent_id)
    except BuildPaused as exc:
        result = BuildResult(exc.status, session.attempt, session.agent_id, exc.messages)
    except (OSError, ValueError, RuntimeError, SyntaxError, KeyboardInterrupt) as exc:
        message = redact(str(exc), session.environ)
        save_json(session.attempt / "build-result.json", {
            "status": "interrupted" if isinstance(exc, KeyboardInterrupt) else "failed",
            "current_file": getattr(session, "current_path", None),
            "completed_files": list(session.completed), "error_type": type(exc).__name__,
            "message": message, "certified": False})
        if isinstance(exc, KeyboardInterrupt):
            raise
        raise BuildError(message) from None
    save_json(session.attempt / "build-result.json", {
        "status": result.status, "agent_id": session.agent_id, "messages": result.messages,
        "completed_files": list(session.completed), "certified": False,
        "model": getattr(getattr(session.client, "target", None), "model", None)})
    return result
