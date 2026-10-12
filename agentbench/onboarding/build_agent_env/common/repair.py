"""Share a stage's correction budget across decoding, validation and review."""
from dataclasses import dataclass
import json

from .errors import BuildPaused, ProviderResponseError, StageResponseError
from .responses import validate_response
from .writer import save_json
from ..openrouter_provider.privacy import contains_secret, redact
from ..openrouter_provider.source_requests import generate_with_source
from ..openrouter_provider.response_metadata import content_contains_secret


def record(stage, prefix, value):
    index = 1 + len(list(stage.glob(f"{prefix}-[0-9]*.json")))
    save_json(stage / f"{prefix}-{index}.json", value)


@dataclass
class RepairBudget:
    remaining: int

    def correction(self, session, stage, prefix, payload, error, previous=None):
        message = redact(str(error), session.environ)[:2048]
        diagnostics = getattr(error, "diagnostics", {})
        details = {"error": message}
        if payload.get("target_path"):
            details["path"] = payload["target_path"]
        if diagnostics:
            details["diagnostics"] = diagnostics
        record(stage, prefix, details)
        session.output_fn(message)
        content = getattr(error, "previous_content", None)
        terminal = isinstance(error, ProviderResponseError) and content is None
        if terminal or self.remaining == 0:
            label = payload.get("target_path")
            raise StageResponseError(f"{label}: {message}" if label else message,
                                     diagnostics=diagnostics) from None
        self.remaining -= 1
        feedback = {"validation_error": message}
        if content is not None:
            feedback["previous_content"] = content
        elif previous is not None:
            feedback["previous_response"] = previous
        clean_payload = {key: value for key, value in payload.items()
                         if key not in {"previous_content", "previous_response", "validation_error"}}
        return {**clean_payload, **feedback}


def request_response(session, payload, *, prompt, schema, stage, budget,
                     response_prefix="response", validation_prefix="validation",
                     validator=None, checkpoint=None, secret_label="Model"):
    base_payload = payload
    while True:
        response = None
        try:
            response = generate_with_source(session, payload, prompt=prompt, schema=schema,
                                            stage=stage, checkpoint=checkpoint)
            if contains_secret(json.dumps(response), session.environ):
                raise StageResponseError(
                    f"{secret_label} response contains a credential; it was not saved or sent back")
            record(stage, response_prefix, response)
            if validator is None:
                validate_response(response, schema, session)
            else:
                validator(response, schema, session)
            return response
        except (BuildPaused, StageResponseError):
            raise
        except ProviderResponseError as exc:
            if exc.previous_content is not None and content_contains_secret(exc.previous_content, session.environ):
                raise StageResponseError(
                    f"{secret_label} response contains a credential; it was not saved or sent back") from None
            payload = budget.correction(session, stage, validation_prefix, base_payload, exc)
        except ValueError as exc:
            # HTTP/transport BuildErrors have no model response and must not consume
            # a content correction or duplicate their own retry policy.
            if response is None:
                raise StageResponseError(redact(str(exc), session.environ)) from None
            payload = budget.correction(session, stage, validation_prefix, base_payload, exc, response)
