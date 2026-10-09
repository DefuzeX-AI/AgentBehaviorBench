"""ABB boundary for BreadFree-Simu's native three-role LangGraph committee.

The selected native entrypoint is
``breadfree.strategies.agent_strategy.build_graph``. It compiles the same
market-analyst -> risk-manager -> fund-manager workflow used by
``AgentStrategy`` during a backtest. The binding invokes that graph directly so
ABB can evaluate the reasoning committee without inventing a broker, downloading
market data, or executing trades.

One Case input can provide the three fields the native graph requires:
``date``, ``market_data`` and ``account_status``. The preferred text form is a
JSON object containing exactly those non-empty string fields. A labeled text
form with ``DATE:``, ``MARKET_DATA:`` and ``ACCOUNT_STATUS:`` sections is also
accepted. Other non-empty text is passed as raw market context with explicit
``not supplied by caller`` sentinels for date and account status; no business
value is guessed. The complete native state is returned as evidence and its unmodified
``final_decision`` string is exposed as ``answer``. RunnableConfig is forwarded
to the native graph so observation callbacks cover the real model calls.

Each invocation is independent, matching the upstream graph's lack of a
checkpointer. Native exceptions and malformed final output remain visible; the
binding does not execute the decision against a broker.
"""

from __future__ import annotations

import asyncio
import json
import re
from collections.abc import Mapping

_FIELDS = ("date", "market_data", "account_status")
_LABELED_INPUT = re.compile(
    r"\A\s*DATE:\s*(?P<date>[^\r\n]+)\s*\r?\n"
    r"MARKET_DATA:\s*(?P<market_data>.*?)\s*\r?\n"
    r"ACCOUNT_STATUS:\s*(?P<account_status>.*?)\s*\Z",
    re.DOTALL | re.IGNORECASE,
)


def _validate_request(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping) or set(value) != set(_FIELDS):
        raise ValueError(
            "Supply exactly date, market_data and account_status as a JSON object"
        )
    request: dict[str, str] = {}
    for field in _FIELDS:
        item = value[field]
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{field} must be a non-empty string")
        request[field] = item.strip()
    return request


def request_from_input(value: object) -> dict[str, str]:
    """Translate ABB's current text input into the native graph input state."""
    if isinstance(value, Mapping) and set(value) == {"message"}:
        value = value["message"]
    if isinstance(value, Mapping):
        return _validate_request(value)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case input must be non-empty text or a request object")

    text = value.strip()
    try:
        decoded = json.loads(text)
    except json.JSONDecodeError:
        match = _LABELED_INPUT.fullmatch(text)
        if not match:
            return {
                "date": "not supplied by caller",
                "market_data": text,
                "account_status": "not supplied by caller",
            }
        decoded = match.groupdict()
    return _validate_request(decoded)


class BreadFreeCommittee:
    def __init__(self) -> None:
        from breadfree.strategies.agent_strategy import build_graph

        self._graph = build_graph()

    async def ainvoke(self, value: object, config=None, **kwargs):
        if self._graph is None:
            raise RuntimeError("BreadFree-Simu binding is closed")
        initial = request_from_input(value)
        initial.update(analyst_view="", risk_view="", final_decision="")
        result = await self._graph.ainvoke(initial, config=config)
        final_decision = result.get("final_decision")
        if not isinstance(final_decision, str) or not final_decision.strip():
            raise RuntimeError("BreadFree-Simu returned no final_decision")
        return {
            "answer": final_decision,
            "date": result.get("date"),
            "market_data": result.get("market_data"),
            "account_status": result.get("account_status"),
            "analyst_view": result.get("analyst_view"),
            "risk_view": result.get("risk_view"),
            "final_decision": final_decision,
        }

    def invoke(self, value: object, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))

    def close(self) -> None:
        self._graph = None


def create_graph() -> BreadFreeCommittee:
    return BreadFreeCommittee()
