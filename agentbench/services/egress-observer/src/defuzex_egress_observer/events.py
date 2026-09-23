"""Egress events, on a stdout prefix of their own so they never mix with model traffic."""
import json

EGRESS_PREFIX = "DEFUZEX_EGRESS "


def emit(event: str, **data: object) -> None:
    print(EGRESS_PREFIX + json.dumps({"event": event, **data}, ensure_ascii=False), flush=True)
