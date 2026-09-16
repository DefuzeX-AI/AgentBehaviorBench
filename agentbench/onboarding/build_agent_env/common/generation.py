"""Generate, validate and install exactly one file before advancing the pipeline."""

import json
from pathlib import Path

from .errors import BuildError, BuildPaused
from .responses import validate_response
from .writer import confined, install_file, save_json
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
            content = target.read_text()
            if contains_secret(content, session.environ):
                raise BuildError("Existing file contains credentials and cannot be sent to the model")
            step.validate(content, session)
        except (ValueError, OSError, SyntaxError) as exc:
            message = redact(str(exc), session.environ)
            save_json(stage / "result.json", {"status": "conflict", "path": step.path, "message": message})
            raise BuildPaused("conflict", [f"{step.path}: {message}; existing file was preserved"]) from None
        session.output_fn(prefix + ": reused existing file")
        status = "reused"
    else:
        content = step.template
        if content is None:
            content = generate_file(step, session, stage, prefix)
        else:
            step.validate(content, session)
        install_file(session.source.directory, step.path, content)
        session.output_fn(prefix + f": saved {target}")
        status = "saved"
    session.completed[step.path] = content
    checkpoint.record_file(step.path, content)
    save_json(stage / "result.json", {"status": status, "path": step.path})


def generate_file(step, session, stage, prefix):
    """Retry only this response with validator feedback, keeping earlier files."""
    schema = json.loads((step.response_schema or SCHEMA).read_text())
    schema["properties"]["path"]["enum"] = [step.path]
    base_payload = {**session.payload(), **step.request_data, "target_path": step.path}
    payload = base_payload
    for index in range(session.settings.repair_attempts + 1):
        session.output_fn(prefix + (": generating" if index == 0 else ": correcting current file"))
        response = session.generate(payload, prompt=step.prompt, schema=schema)
        if contains_secret(json.dumps(response), session.environ):
            raise BuildError("Model response contains a credential; it was not saved or sent back")
        save_json(stage / f"response-{index + 1}.json", response)
        try:
            validate_response(response, schema, session)
            if response["status"] != "complete":
                raise BuildPaused(response["status"], response["missing_information"])
            content = step.render(response, session) if step.render else response["content"]
            if contains_secret(content, session.environ):
                raise BuildError("Rendered file contains credentials")
            if not content.strip():
                raise BuildError("Generated file content is empty")
            (stage / "candidate").write_text(content)
            step.validate(content, session)
            return content
        except BuildPaused:
            raise
        except (ValueError, OSError, SyntaxError) as exc:
            message = redact(str(exc), session.environ)
            save_json(stage / f"validation-{index + 1}.json", {"path": step.path, "error": message})
            if index == session.settings.repair_attempts:
                raise BuildError(f"{step.path}: {message}") from None
            payload = {**base_payload,
                       "previous_response": response, "validation_error": message}
    raise AssertionError("unreachable")
