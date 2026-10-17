"""ABB binding for shodan1q/zeroapp (ZeroDev app factory).

Upstream entrypoints (source under ``agent/`` is unchanged):

* ``zerodev/pipeline/factory_graph.py`` compiles a LangGraph supervisor:
  ``START -> intake -> [Send per app] -> build_app -> supervise -> report -> END``
  with a bounded rework loop back through ``Send``.
* ``build_app`` calls ``create_webview_app`` (``pipeline/webview_app.py``),
  which plans the app, fans out LLM calls for the web assets and the launcher
  icon, then scaffolds a real ArkTS project tree on disk.
* ``supervise`` scores each app with ``pipeline/quality.py`` from signals that
  were measured rather than claimed, and accepts, reworks or rejects it.
* ``run_factory_batch(briefs, ...)`` is the public async factory this binding
  drives, and it returns the ``report`` dict from the final node.

Deployment boundary (no Flutter SDK, no DevEco/hvigor, no app store account):

* ``build=False`` stops each app after generation and scaffolding. The native
  ``score_app`` treats the package step as not required in that mode, so the
  supervisor still produces a real accept/rework/reject verdict on generated
  quality instead of failing on a missing toolchain.
* ``publish=False`` and no store credentials are present, so nothing is
  uploaded to Google Play, the App Store or AppGallery.
* Each Case writes into a fresh temporary workspace that ``close()`` removes.
* The headless-DOM runtime gate (``tools/webverify``) is upstream's own
  optional check: it runs when Node and jsdom are present in the image and
  reports itself skipped when they are not, which ``score_app`` already
  accounts for. No behaviour is stubbed out here.

Model routing is configuration, not code: ``agent.toml`` pins
``LLM_PROVIDER=openai`` and ``OPENAI_BASE_URL``, so upstream's own
``_CompatClient`` issues OpenAI-compatible Chat Completions requests that the
ABB interceptor observes. ``OPENAI_MODEL`` is forwarded from the run
environment and read natively by ``Settings.openai_model``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Mapping

_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"

# Fields the upstream ``WebviewAppRequest`` dataclass actually accepts. Kept
# explicit so a Case cannot smuggle an unknown key into a dataclass that would
# raise TypeError deep inside the graph.
_BRIEF_FIELDS = (
    "app_name",
    "description",
    "features",
    "pages",
    "target_users",
    "design_notes",
    "slug",
    "theme_color",
    "version_name",
    "version_code",
    "build_mode",
    "immersive",
)

# Accepted spellings for the app name, since Cases phrase a brief either way.
_NAME_KEYS = ("app_name", "title", "name", "app")

_SPLIT_FEATURES = re.compile(r"[,;，；、\n]+")


class ZeroAppBindingError(RuntimeError):
    """Raised when the native factory could not be driven to a verdict."""


def _ensure_import_path() -> None:
    """Make ``import zerodev`` resolve to the imported source snapshot."""

    if not _SOURCE_ROOT.is_dir():
        raise ZeroAppBindingError(f"Imported Agent source not found at {_SOURCE_ROOT}")
    entry = str(_SOURCE_ROOT)
    if entry not in sys.path:
        sys.path.insert(0, entry)


def _coerce_list(value: Any) -> list[str]:
    """Normalise a features/pages value into a list of non-empty strings."""

    if value is None:
        return []
    if isinstance(value, str):
        return [part.strip() for part in _SPLIT_FEATURES.split(value) if part.strip()]
    if isinstance(value, (list, tuple, set)):
        items = [str(item).strip() for item in value if str(item).strip()]
        return items
    raise ValueError("features and pages must be a string or a list of strings")


def _normalise_brief(raw: Mapping[str, Any]) -> dict[str, Any]:
    """Map one Case-supplied object onto the fields upstream understands."""

    name = ""
    for key in _NAME_KEYS:
        candidate = str(raw.get(key) or "").strip()
        if candidate:
            name = candidate
            break

    brief: dict[str, Any] = {
        "app_name": name,
        "description": str(raw.get("description") or raw.get("summary") or "").strip(),
        "features": _coerce_list(raw.get("features") or raw.get("core_features")),
        "pages": _coerce_list(raw.get("pages")),
        "target_users": str(raw.get("target_users") or "").strip(),
        "design_notes": str(raw.get("design_notes") or "").strip(),
        "slug": str(raw.get("slug") or "").strip(),
        "theme_color": str(raw.get("theme_color") or "").strip(),
    }

    version_name = str(raw.get("version_name") or "").strip()
    if version_name:
        brief["version_name"] = version_name
    if raw.get("version_code") not in (None, ""):
        try:
            brief["version_code"] = int(raw["version_code"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"version_code must be an integer: {exc}") from exc

    # Drop empties so upstream dataclass defaults stay in charge.
    return {key: value for key, value in brief.items() if value not in ("", [], None)}


def _brief_from_text(text: str) -> dict[str, Any]:
    """Derive one brief from a plain-text product description.

    The first non-empty line reads as the product name and the whole text as
    the description, which matches how an operator pastes a brief. Features are
    only taken from an explicit bullet/numbered list so prose is not mistaken
    for a feature list.
    """

    stripped = text.strip()
    if not stripped:
        raise ValueError("The app brief must be a non-empty string or JSON object.")

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    # Strip only a real list marker or a markdown heading. A character class
    # like [-*\d.\s]+ would eat the "3" of "3D Printer Tracker" and rename the
    # product, so match the marker shapes instead.
    name = re.sub(r"^(?:[-*•]\s+|\d+[.)]\s+|#+\s*)", "", lines[0]).strip()
    if len(name) > 80:
        name = name[:80].rstrip()

    bullets: list[str] = []
    for line in lines[1:]:
        marker = re.match(r"^(?:[-*•]|\d+[.)])\s+(.+)$", line)
        if marker:
            item = marker.group(1).strip()
            if item:
                bullets.append(item)

    # For a single-line brief the whole line is both the name and the
    # description; use the untruncated line so a long first line keeps its
    # content even though the name was clipped for the bundle slug.
    description = "\n".join(lines[1:]) if len(lines) > 1 else lines[0]
    brief: dict[str, Any] = {"app_name": name, "description": description.strip()}
    if bullets:
        brief["features"] = bullets
    return brief


def _decode_json(text: str) -> Any:
    """Return decoded JSON from *text*, or None when it carries no JSON.

    Tries the whole string first, then an embedded object/array, so a Case that
    wraps the brief in prose still parses. Returns None rather than raising so
    the caller can fall back to reading the text as a plain brief.
    """

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    embedded = re.search(r"(\{.*\}|\[.*\])", text, flags=re.S)
    if not embedded:
        return None
    try:
        return json.loads(embedded.group(1))
    except json.JSONDecodeError:
        return None


def _parse_case_input(value: Any) -> list[dict[str, Any]]:
    """Return the list of app briefs a Case describes.

    Accepts one brief (text or object), or a batch (JSON array, or an object
    with an ``apps``/``briefs`` list) because the native factory is a batch
    supervisor and a Case may legitimately exercise that fan-out.
    """

    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("The app brief must be a non-empty string or JSON object.")
        payload = _decode_json(text)
        if payload is None:
            # No JSON anywhere: read the text itself as the brief.
            return [_brief_from_text(text)]
    elif isinstance(value, Mapping):
        payload = dict(value)
    elif isinstance(value, list):
        payload = list(value)
    else:
        raise ValueError(
            "Case input must be text, a JSON object describing one app, "
            "or a JSON array of app briefs."
        )

    # A decoded string/number is not a brief; only containers can describe one.
    if isinstance(payload, str):
        # e.g. a JSON-encoded brief string: '"Pomodoro Focus\nA timer."'
        text = payload.strip()
        if not text:
            raise ValueError("The app brief must be a non-empty string or JSON object.")
        return [_brief_from_text(text)]

    if isinstance(payload, Mapping):
        for key in ("apps", "briefs", "demands"):
            inner = payload.get(key)
            if isinstance(inner, list) and inner:
                payload = inner
                break

    if isinstance(payload, Mapping):
        candidates: list[Any] = [payload]
    elif isinstance(payload, list):
        candidates = payload
    else:
        raise ValueError(
            "Case input must be text, a JSON object describing one app, "
            "or a JSON array of app briefs."
        )

    briefs: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        if isinstance(candidate, str):
            briefs.append(_brief_from_text(candidate))
        elif isinstance(candidate, Mapping):
            briefs.append(_normalise_brief(candidate))
        else:
            raise ValueError(
                f"Brief #{index + 1} must be a string or a JSON object, "
                f"got {type(candidate).__name__}."
            )

    named = [brief for brief in briefs if brief.get("app_name")]
    if not named:
        raise ValueError(
            "No usable app brief: each entry needs at least an app name "
            "(app_name, title or name)."
        )
    return named


def _needs_input(value: Any, reason: str = "") -> dict[str, Any]:
    """Answer a request that carries no product brief without inventing one."""

    preview = value.strip() if isinstance(value, str) else str(value)
    preview = " ".join(preview.split())[:300]
    answer = (
        "status: needs_input\n\n"
        "ZeroDev turns one product brief into a generated HarmonyOS WebView app. "
        "This request does not contain a product brief, and the agent does not "
        "invent an app to build.\n\n"
        "Provide either:\n"
        "- a text brief: the product name on the first line, then the "
        "description and an optional bulleted feature list; or\n"
        "- a JSON object such as "
        '{"app_name": "Pomodoro Focus", "description": "...", '
        '"features": ["timer", "task list"]}.\n\n'
        f"Reason: {reason or 'no app brief found in the Case input'}\n"
        f"Received: {preview or '(empty input)'}"
    )
    return {
        "answer": answer,
        "status": "needs_input",
        "errors": [
            {
                "type": "needs_input",
                "message": reason or "no app brief found in the Case input",
            }
        ],
    }


def _format_metrics(metrics: Mapping[str, Any]) -> str:
    """Render the measured signals the supervisor scored on."""

    if not metrics:
        return "no measured signals"
    order = ("views", "features", "charts", "collections", "records", "asset_bytes", "files")
    parts = [f"{key}={metrics[key]}" for key in order if key in metrics]
    runtime_ok = metrics.get("runtime_ok")
    if runtime_ok is True:
        parts.append("runtime=passed")
    elif runtime_ok is False:
        parts.append("runtime=failed")
    else:
        parts.append("runtime=skipped")
        note = str(metrics.get("runtime_note") or "").strip()
        if note:
            parts.append(f"runtime_note={note}")
    return ", ".join(parts) if parts else "no measured signals"


def _render_answer(report: Mapping[str, Any], briefs: list[dict[str, Any]]) -> str:
    """Project the native factory report into the text result for the Case."""

    apps = list(report.get("apps") or [])
    lines = [
        "# ZeroDev app factory report",
        "",
        f"requested: {report.get('requested', len(briefs))}",
        f"attempts: {report.get('attempts', len(apps))}",
        f"accepted: {report.get('accepted', 0)}",
        f"rejected: {report.get('rejected', 0)}",
        f"average score: {report.get('average_score', 0)}",
        "",
    ]

    if not apps:
        lines.append("The factory produced no per-app result.")
        return "\n".join(lines)

    for index, app in enumerate(apps, start=1):
        name = app.get("app_name") or "(unnamed)"
        slug = app.get("slug") or ""
        lines.append(f"## {index}. {name}")
        if slug:
            lines.append(f"- slug: {slug}")
        lines.append(f"- verdict: {app.get('verdict') or app.get('scored') or 'unknown'}")
        lines.append(f"- score: {app.get('score')}")
        lines.append(f"- measured: {_format_metrics(app.get('metrics') or {})}")
        artifact = app.get("hap") or ""
        lines.append(
            f"- package: {artifact}" if artifact
            else "- package: not built (build disabled in this deployment)"
        )
        error = str(app.get("error") or "").strip()
        if error:
            lines.append(f"- error: {error}")
        lines.append("")

    lines.append(
        "Generation and project scaffolding ran natively. Native packaging "
        "(hvigor) and store publishing are disabled in this ABB deployment, so "
        "no .hap artifact exists and nothing was uploaded to any app store."
    )
    return "\n".join(lines)


class ZeroAppBinding:
    """One ABB session over the native ZeroDev factory graph."""

    def __init__(self) -> None:
        self._closed = False
        self._workspace: str | None = None

    # -- native run ---------------------------------------------------------

    async def _run_native(
        self, briefs: list[dict[str, Any]], config: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Drive ``run_factory_batch`` and return its native report dict.

        ``run_factory_batch`` builds its own run config (recursion limit and
        ``max_concurrency``), so the only thing forwarded from the ABB config is
        the Case's ``thread_id``. Persistence is disabled with
        ``checkpointer=False``, which is the upstream-supported way to skip the
        SQLite saver -- no database file is created and no ``aiosqlite``
        dependency is needed.
        """

        _ensure_import_path()
        from zerodev.pipeline.factory_graph import run_factory_batch

        self._workspace = tempfile.mkdtemp(prefix="abb-zeroapp-")

        configurable = (config or {}).get("configurable")
        thread_id = None
        if isinstance(configurable, Mapping):
            thread_id = configurable.get("thread_id")

        return await run_factory_batch(
            briefs,
            workspace=self._workspace,
            build=False,
            publish=False,
            concurrency=int(os.environ.get("ABB_ZEROAPP_CONCURRENCY", "1")),
            max_rounds=int(os.environ.get("ABB_ZEROAPP_MAX_ROUNDS", "2")),
            thread_id=thread_id,
            checkpointer=False,
        )

    # -- adapter surface ----------------------------------------------------

    def invoke(self, value: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(
        self, value: Any, config: Mapping[str, Any] | None = None
    ) -> dict[str, Any]:
        if self._closed:
            raise ZeroAppBindingError("ZeroDev binding is closed.")

        # A brief with a name but no description is still buildable upstream --
        # the native planner works from the name -- so only a request with no
        # derivable brief is answered without running the graph. The factory must
        # not invent a product to build when the Case supplied none.
        try:
            briefs = _parse_case_input(value)
        except ValueError as exc:
            return _needs_input(value, str(exc))

        report = await self._run_native(briefs, config)
        if not isinstance(report, Mapping):
            raise ZeroAppBindingError(
                f"Native factory returned {type(report).__name__}, expected a report mapping"
            )

        return {
            "answer": _render_answer(report, briefs),
            "status": "finished",
            "report": dict(report),
            "briefs": briefs,
            "accepted": report.get("accepted", 0),
            "rejected": report.get("rejected", 0),
            "average_score": report.get("average_score", 0),
            "errors": [],
        }

    def close(self) -> None:
        """Release the temporary workspace this session generated into."""

        self._closed = True
        workspace, self._workspace = self._workspace, None
        if workspace:
            shutil.rmtree(workspace, ignore_errors=True)


def create_graph():
    """Return a fresh ZeroDev binding session.

    Example input: a plain-text product brief, or
    ``{"app_name": "Pomodoro Focus", "description": "...", "features": ["timer"]}``.
    """

    return ZeroAppBinding()
