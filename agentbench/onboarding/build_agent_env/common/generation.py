"""Generate, validate and install exactly one file before advancing the pipeline."""

import json
from pathlib import Path

from .errors import BuildError, BuildPaused, StageResponseError
from .repair import RepairBudget, request_response
from .writer import confined, install_file, save_json
from .review import review_file
from .checkpoint import digest
from ..openrouter_provider.privacy import contains_secret, redact

SCHEMA = Path(__file__).parents[1] / "openrouter_provider/assets/file-response.schema.json"


def run_step(step, session, checkpoint, index, total):
    """Complete one file and persist its checkpoint before the next model call."""
    session.current_path = step.path
    prefix = f"[{index}/{total}] {step.path}"
    stage = session.attempt / "steps" / f"{index:02d}-{Path(step.path).name}"
    stage.mkdir(parents=True)
    target = confined(session.source.directory, step.path)
    if target.exists():
        try:
            if not target.is_file() or target.stat().st_size > session.settings.max_response_bytes:
                raise BuildError("Existing file is not a bounded regular file")
            content = target.read_text(encoding="utf-8")
            if contains_secret(content, session.environ):
                raise BuildError("Existing file contains credentials and cannot be sent to the model")
            step.validate(content, session)
            if step.template is None and checkpoint.data.get("reviews", {}).get(step.path) != digest(content):
                review_file(step, content, session, stage, prefix, checkpoint=checkpoint)
        except (ValueError, OSError, SyntaxError) as exc:
            message = redact(str(exc), session.environ)
            save_json(stage / "result.json", {"status": "conflict", "path": step.path, "message": message})
            raise BuildPaused("conflict", [f"{step.path}: {message}; existing file was preserved"]) from None
        session.output_fn(prefix + ": reused existing file")
        status = "reused"
    else:
        content = step.template
        if content is None:
            content = generate_file(step, session, stage, prefix, checkpoint=checkpoint)
        else:
            step.validate(content, session)
        install_file(session.source.directory, step.path, content)
        session.output_fn(prefix + f": saved {target}")
        status = "saved"
    session.completed[step.path] = content
    checkpoint.record_file(step.path, content)
    if step.template is None:
        checkpoint.record_review(step.path, content)
    save_json(stage / "result.json", {"status": status, "path": step.path})


def generate_file(step, session, stage, prefix, *, checkpoint=None):
    """Retry only this response with validator feedback, keeping earlier files."""
    schema = json.loads((step.response_schema or SCHEMA).read_text(encoding="utf-8"))
    schema["properties"]["path"]["enum"] = [step.path]
    base_payload = {**session.payload(), **step.request_data, "target_path": step.path}
    payload = base_payload
    budget = RepairBudget(session.settings.repair_attempts)
    while True:
        session.output_fn(prefix + (": generating" if payload is base_payload else ": correcting current file"))
        response = request_response(session, payload, prompt=step.prompt, schema=schema,
                                    stage=stage, checkpoint=checkpoint, budget=budget)
        try:
            if response["status"] != "complete":
                raise BuildPaused(response["status"], response["missing_information"])
            content = step.render(response, session) if step.render else response["content"]
            if contains_secret(content, session.environ):
                raise StageResponseError("Rendered file contains credentials")
            if not content.strip():
                raise BuildError("Generated file content is empty")
            (stage / "candidate").write_text(content, encoding="utf-8")
            step.validate(content, session)
            review_file(step, content, session, stage, prefix, checkpoint=checkpoint, budget=budget)
            return content
        except (BuildPaused, StageResponseError):
            raise
        except (ValueError, OSError, SyntaxError) as exc:
            payload = budget.correction(session, stage, "validation", base_payload, exc, response)
