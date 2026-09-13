"""Trace serialization; failures are sanitized at the output boundary."""
import json
from ..error import InterceptionFailure
from ..security.redaction import redact

TRACE_PREFIX = "DEFUZEX_TRACE "

def emit(event: str, **data: object) -> None:
    print(
        TRACE_PREFIX + json.dumps({"event": event, **data}, ensure_ascii=False),
        flush=True,
    )


def failure_fields(failure: InterceptionFailure, secrets: tuple[str, ...] = ()) -> dict[str, object]:
    return redact(failure.to_event_fields(), secrets)
