"""Expose CSGOTrading's single-trading-day entry point without changing upstream.

Native contract (verified against the pinned revision):

* ``run.main()`` is the public CLI. It discovers ``config/<name>.yaml``, then for
  every calendar day in ``--start-date .. --end-date`` calls
  ``run.run_single_experiment(config_path, trading_date, use_local_db=True)``,
  which loads the config through ``util.config.ConfigParser``, initialises the
  SQLite database, creates/loads the portfolio for that experiment, enforces
  chronological trading dates and runs ``graph.workflow.AgentWorkflow``.
* ``run.main()`` cannot run as shipped: it resolves the config as
  ``<repo>/src/config/<name>.yaml`` and creates ``<repo>/src/logs``, but this
  repository has no ``src/`` directory. The binding therefore calls the same
  single-day function with the real ``config/<name>.yaml`` path instead of the
  broken batch wrapper. No upstream file is modified.
* ``agents.registry.AgentRegistry.run_registry()`` is the project's own registry
  initialisation, but no upstream module calls it; without it every
  ``get_agent_func_by_key`` returns ``None`` and graph compilation fails. The
  binding performs that documented initialisation once per Agent instance, the
  way a service lifecycle would.

Deployment (see ``requirement.md``): one Case input selects the trading day and,
optionally, the items to analyse, and every Case is bounded to
``MAX_ITEMS_PER_RUN`` items because each item costs two model calls (risk control
and the portfolio manager). The market data is a captured public snapshot applied
by ABB's ``install/`` mechanism at ``agent/apis/cs2market/cs2_data.csv``; the
deployment makes no live market call. The analysis itself is the upstream
direct-LLM pipeline of ``Direct-ds.yaml``: risk control and the portfolio manager
are the only model calls per item, and the agent's own prompts are used unchanged.

Input: plain text, or exactly ``{"message": text}``. The text may contain one
``YYYY-MM-DD`` trading day (defaults to the newest day in the snapshot) and item
names copied verbatim from the selected config (defaults to the first
``MAX_ITEMS_PER_RUN`` configured items).
Config: the adapter's run configuration is attached as ambient LangChain context
around the native call, because the native lifecycle accepts no run config; it is
never passed as an unsupported keyword.
Output: a mapping whose ``summary`` field is the human-readable run report;
``portfolio`` and ``decisions`` carry the structured result.
Errors: a request for a trading day or item set this deployment cannot serve is
answered as a refusal (``status = "refused"``, no pipeline run), as the unit's
requirement asks; malformed input and native failures propagate; nothing is
turned into a fake success.
Ownership: the instance owns the SQLite file it creates under ``CS2_DB_PATH``.
"""

from __future__ import annotations

import csv
import os
import re
import sqlite3
import sys
import tempfile
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

UNIT_ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = UNIT_ROOT / "agent"
DEFAULT_CONFIG = "Direct-ds.yaml"
DEFAULT_DB_PATH = "/tmp/abb-csgotrading/cs2.db"

# Upstream's own batch CLI loops every configured item, and each item costs two
# model calls. One Case is bounded to this many items so a run stays inside the
# Case time budget; the input may name any subset of at most this size.
MAX_ITEMS_PER_RUN = 4

DATE_PATTERN = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")

# Reporting only: the binding never writes through these.
_PORTFOLIO_SQL = ("SELECT id, cashflow, total_assets, positions, trading_date "
                  "FROM cs2_portfolio WHERE config_id = ? AND trading_date = ?")
_DECISION_SQL = ("SELECT item_name, action, quantity, price, justification "
                 "FROM cs2_decision WHERE portfolio_id = ? ORDER BY item_name")


def _market_csv() -> Path:
    return AGENT_ROOT / "apis" / "cs2market" / "cs2_data.csv"


class InputRefused(ValueError):
    """The input asks for market data or items this deployment cannot serve."""


def _load_yaml_config(name: str) -> dict:
    import yaml

    path = AGENT_ROOT / "config" / name
    if not path.is_file():
        raise ValueError(f"Unknown configuration {name!r}; expected config/{name}")
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def _snapshot_dates() -> list[str]:
    """Distinct trading days present in the applied market snapshot."""
    path = _market_csv()
    if not path.is_file():
        raise RuntimeError(
            f"Market snapshot missing at {path}; the deployment's install/ input was not applied")
    dates = set()
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        for row in csv.DictReader(handle):
            raw = (row.get("batch_id") or row.get("date") or "").strip()
            if len(raw) >= 10 and raw[4] == "-" and raw[7] == "-":
                dates.add(raw[:10])
    if not dates:
        raise RuntimeError(f"No usable trading day found in {path}")
    return sorted(dates)


class CsgoTradingDay:
    """Owns one upstream direct-LLM trading pipeline for one trading day."""

    def __init__(self, config_name: str = DEFAULT_CONFIG):
        self._config_name = config_name
        self._manifest = _load_yaml_config(config_name)
        self._configured_items = list(self._manifest["tickers"])
        self._closed = True
        self._prepared = False
        self._db_path = ""
        self._types = None

    # -- lifecycle ---------------------------------------------------------
    def _prepare(self) -> None:
        if self._prepared:
            return
        # database/cs2_sqlite_setup.py reads this at import time and creates the
        # parent directory, so it must be set before the upstream import.
        self._db_path = os.environ.setdefault("CS2_DB_PATH", DEFAULT_DB_PATH)
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        if str(AGENT_ROOT) not in sys.path:
            sys.path.insert(0, str(AGENT_ROOT))

        from agents.registry import AgentRegistry
        from util.cs2_db_helper import cs2_db_initialize, get_cs2_db

        AgentRegistry.run_registry()
        if get_cs2_db() is None:
            cs2_db_initialize(use_local_db=True)

        import run as upstream_run

        self._run_single_experiment = upstream_run.run_single_experiment
        self._prepared = True
        self._closed = False

    def close(self) -> None:
        self._prepared = False
        self._closed = True

    # -- input -------------------------------------------------------------
    def _parse(self, value) -> tuple[str, list[str]]:
        if isinstance(value, Mapping):
            if set(value) != {"message"}:
                raise ValueError("Supply exactly one 'message' field")
            value = value["message"]
        if not isinstance(value, str) or not value.strip():
            raise ValueError("message must be a non-empty string")

        available = _snapshot_dates()
        found = DATE_PATTERN.findall(value)
        if len(found) > 1:
            raise InputRefused(f"Supply at most one trading day; got {sorted(set(found))}")
        if found:
            trading_date = found[0]
            if trading_date not in available:
                raise InputRefused(
                    f"No market data for {trading_date}; this deployment has "
                    f"{', '.join(available)} (snapshot-captured market data)")
        else:
            trading_date = available[-1]

        lowered = value.lower()
        selected = [item for item in self._configured_items if item.lower() in lowered]
        if len(selected) > MAX_ITEMS_PER_RUN:
            raise InputRefused(
                f"Name at most {MAX_ITEMS_PER_RUN} items; got {len(selected)} "
                f"({', '.join(selected)})")
        if not selected:
            selected = self._configured_items[:MAX_ITEMS_PER_RUN]
        return trading_date, selected

    def _config_path(self, items: list[str]) -> tuple[str, str]:
        """Return (config path, experiment name) for this input."""
        if len(items) == len(self._configured_items):
            return str(AGENT_ROOT / "config" / self._config_name), self._manifest["exp_name"]

        exp_name = f"{self._manifest['exp_name']}-{len(items)}items"
        narrowed = {**self._manifest, "exp_name": exp_name, "tickers": items}
        import yaml

        directory = Path(tempfile.mkdtemp(prefix="abb-csgo-config-", dir=Path(self._db_path).parent))
        path = directory / f"{exp_name}.yaml"
        with path.open("w", encoding="utf-8") as handle:
            yaml.safe_dump(narrowed, handle, allow_unicode=True, sort_keys=False)
        return str(path), exp_name

    # -- reporting ---------------------------------------------------------
    def _report(self, exp_name: str, trading_date: str) -> tuple[dict, list[dict]]:
        stamp = datetime.fromisoformat(trading_date).isoformat()
        connection = sqlite3.connect(self._db_path)
        connection.row_factory = sqlite3.Row
        try:
            config_row = connection.execute(
                "SELECT id FROM cs2_config WHERE exp_name = ?", (exp_name,)).fetchone()
            if config_row is None:
                raise RuntimeError(f"Upstream run left no config row for {exp_name!r}")
            row = connection.execute(_PORTFOLIO_SQL, (config_row["id"], stamp)).fetchone()
            if row is None:
                raise RuntimeError(
                    f"Upstream run left no portfolio row for {exp_name!r} on {trading_date}")
            import json

            positions = row["positions"]
            if isinstance(positions, str):
                positions = json.loads(positions)
            portfolio = {
                "id": row["id"],
                "cashflow": row["cashflow"],
                "total_assets": row["total_assets"],
                "trading_date": row["trading_date"],
                "positions": positions,
            }
            decisions = [dict(record) for record in
                         connection.execute(_DECISION_SQL, (row["id"],))]
        finally:
            connection.close()
        return portfolio, decisions

    def _summary(self, trading_date: str, config_name: str, portfolio: dict,
                 decisions: list[dict], elapsed: float) -> str:
        lines = [
            f"CS2 trading run — config {config_name} — trading day {trading_date}",
            f"Items analysed: {len(decisions)} of {len(self._configured_items)} configured "
            f"(this deployment bounds one run to {MAX_ITEMS_PER_RUN} items)",
            f"Portfolio {portfolio['id']}: cash {portfolio['cashflow']:.2f}, "
            f"total assets {portfolio['total_assets']:.2f}, "
            f"{len(portfolio['positions'])} position(s)",
            "Decisions:",
        ]
        if not decisions:
            lines.append("- (none recorded)")
        for decision in decisions:
            lines.append(
                f"- {decision['item_name']}: {decision['action']} {decision['quantity']} "
                f"@ {decision['price']} — {decision['justification']}")
        lines.append(f"Upstream time cost: {elapsed:.2f} s")
        return "\n".join(lines)

    # -- invocation --------------------------------------------------------
    def invoke(self, value, config=None) -> dict:
        if self._closed or not self._prepared:
            raise RuntimeError("Binding is closed")
        try:
            trading_date, items = self._parse(value)
        except InputRefused as exc:
            return {
                "summary": f"Refused: {exc}. No trading run was executed and the portfolio is unchanged.",
                "status": "refused",
                "trading_date": None,
                "config": None,
                "items": [],
                "portfolio": None,
                "decisions": [],
                "elapsed_sec": 0.0,
            }
        config_path, exp_name = self._config_path(items)
        # ``AgentWorkflow.run`` takes no run configuration, so the adapter's
        # configuration (callbacks, tags, metadata, limits) is attached as ambient
        # LangChain context instead of being passed as an unsupported keyword. This
        # is how the internal graph's node and model calls stay observable.
        from langchain_core.runnables.config import set_config_context

        with set_config_context(dict(config or {})) as invocation_context:
            elapsed = invocation_context.run(
                self._run_single_experiment, config_path, trading_date, True)
        portfolio, decisions = self._report(exp_name, trading_date)
        return {
            "summary": self._summary(trading_date, exp_name, portfolio, decisions, elapsed),
            "trading_date": trading_date,
            "config": exp_name,
            "items": [decision["item_name"] for decision in decisions],
            "portfolio": portfolio,
            "decisions": decisions,
            "elapsed_sec": elapsed,
        }


def create_graph():
    """Return a fresh binding; example input: {'message': 'Trading day 2026-10-18'}."""
    instance = CsgoTradingDay()
    instance._prepare()
    return instance
