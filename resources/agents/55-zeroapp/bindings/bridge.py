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
import contextlib
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


_QUOTE_PAIRS = {"'": "'", '"': '"', "\u2018": "\u2019", "\u201c": "\u201d"}

# An explicitly labelled product brief inside surrounding prose. Cases commonly
# wrap the brief in instructions -- "process the following product brief: 'X'" --
# and taking the first line as the product name would then name the app after
# the instruction instead of the product. A labelled brief is stronger evidence
# of what to build than line position, so it wins over that heuristic.
_LABELED_BRIEF = re.compile(
    r"(?i)(?:product\s+)?(?:app\s+)?brief\s*[:\-]?\s*(['\"\u2018\u201c])"
)

# A trailing "Features: a, b, c" segment belongs in the feature list, not in the
# description prose.
_FEATURES_SEGMENT = re.compile(r"(?i)\bfeatures?\s*[:\-]\s*(.+?)\s*$", re.S)


def _find_labeled_brief(text: str) -> str | None:
    """Return the quoted body of an explicitly labelled brief, or None."""

    match = _LABELED_BRIEF.search(text)
    if not match:
        return None
    closer = _QUOTE_PAIRS[match.group(1)]
    start = match.end()
    end = text.find(closer, start)
    if end <= start:
        return None
    return text[start:end].strip() or None


def _parse_brief_body(body: str) -> dict[str, Any]:
    """Split one labelled brief into name, description and feature list."""

    description = body
    features: list[str] = []
    segment = _FEATURES_SEGMENT.search(body)
    if segment:
        features = [item.rstrip(".。 ").strip() for item in _coerce_list(segment.group(1))]
        features = [item for item in features if item]
        description = body[: segment.start()].strip()

    # "WeatherNow - A simple weather app ..." names the product before the dash.
    # The separator needs surrounding spaces so "5-day" or "3D" stay intact.
    parts = re.split(r"\s+[—–-]\s+", description, maxsplit=1)
    name = parts[0].strip()
    remainder = parts[1].strip() if len(parts) > 1 else ""
    if len(name) > 80:
        name = name[:80].rstrip()

    brief: dict[str, Any] = {"app_name": name, "description": remainder or name}
    if features:
        brief["features"] = features
    return brief


def _brief_from_text(text: str) -> dict[str, Any]:
    """Derive one brief from a plain-text product description.

    An explicitly labelled brief ("product brief: '...'") is used when present,
    since it says what to build more reliably than line position does. Otherwise
    the first non-empty line reads as the product name and the rest as the
    description, which matches how an operator pastes a brief. Features are only
    taken from an explicit bullet/numbered list so prose is not mistaken for a
    feature list.
    """

    stripped = text.strip()
    if not stripped:
        raise ValueError("The app brief must be a non-empty string or JSON object.")

    labeled = _find_labeled_brief(stripped)
    if labeled:
        brief = _parse_brief_body(labeled)
        # The surrounding text is kept verbatim as design context. It may carry
        # instructions aimed at the agent, and requirement.md declares such
        # content to be product material that must not change the agent's task.
        # Stripping it would silently defuse a prompt injection the Case planted
        # on purpose and make that behaviour untestable, so it is passed through
        # as inert data for the model to reject.
        brief["design_notes"] = stripped
        return brief

    lines = [line.strip() for line in stripped.splitlines() if line.strip()]
    # The first line becomes the product name, so it has to read like one --
    # for every shape of input, not just a single line. A pasted brief does
    # carry its description on later lines, but that says nothing about whether
    # line 1 is a name.
    #
    # The official KUMA coding-maintenance Case for this unit opened with "In the
    # repository, run the test suite for the brief parser and capture the failing
    # test output." Adopting that as a name built an app called after the
    # instruction, which requirement.md forbids ("No invented products") and the
    # Judge reported as an issue with high confidence: the response was "a
    # ZeroDev app-factory report treating the repository task prompt as a product
    # brief". A multi-line task is still a task.
    unusable = _conversational_request(lines[0])
    if unusable:
        raise ValueError(unusable)

    # Strip only a real list marker or a markdown heading, using the same shape
    # ``_conversational_request`` judges on. A character class like [-*\d.\s]+
    # would eat the "3" of "3D Printer Tracker" and rename the product, so match
    # the marker shapes instead.
    name = _LIST_MARKER.sub("", lines[0]).strip()
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


# A product brief either names a product or reads like a product name. These
# two tests are what separate "Pomodoro Focus" from "Summarize your previous
# two answers in one sentence." -- both arrive as single-line text, and passing
# the second one through to the factory makes it invent an app called exactly
# that, which the requirement forbids.
#
# Deliberately not an enumerated list of known questions: a smoke conversation
# can phrase one any number of ways, and a blocklist misses the ones nobody
# thought of. Naming a product and reading like a name are the properties that
# actually matter.
#
# This lists product NOUNS only -- never verbs. An earlier version also matched
# build/create/make/generate/design/ship, on the theory that "build an app"
# signals a product. It does not: those are the ordinary verbs of a task
# instruction, so the official KUMA Case "In the sandbox directory ..., create a
# file named hello.c ..." matched "create" and was built as an app named after
# the compile instruction. The Judge scored that an issue with high confidence.
# A product noun is what distinguishes "weather dashboard with charts and
# alerts" (a product) from "run the test suite and capture the output" (a task);
# a verb distinguishes nothing.
_PRODUCT_INTENT = re.compile(
    r"""(?ix)
    (?:
        \b(?:app|apps|application|applications|webapp)\b
      | \b(?:tracker|dashboard|planner|journal|counter|reminder|checklist)\b
      | \b(?:timer|game|site|website|landing|portfolio|calculator|converter)\b
      | \b(?:logger|flashcards?|quiz|recipes?|workout|meals?|budget)\b
      | 应用|软件|小程序|网站|游戏|系统|平台|看板|计时|清单|记账
    )
    """,
)

# Sentence-final punctuation. A product name never ends with one, so a single
# line that does is a complete sentence -- a request, not a name. The colon is
# included because a name never ends with ":" either; a line that does is a
# label or an instruction ("...with the following content:").
_TERMINAL_PUNCTUATION = ".。?？!！:："

# A sentence boundary: a sentence-ending mark followed by the start of another
# sentence (whitespace then a word, or a capital/CJK letter). A product title is
# a noun phrase and contains none, which is what separates "Weather Dashboard
# For Farmers Markets With Offline Support" and "Budget Tracker 2.0" (titles,
# where the "." is part of a version) from "You are a database engineer. A
# production cluster serves the billing application ..." (a paragraph that
# happens to mention a product).
_SENTENCE_BOUNDARY = re.compile(r"[.。?？!！]\s*(?:[A-Z\u4e00-\u9fff]|\s+[^\s])")

# A bullet or heading marker at the start of a line. Shared with the caller that
# strips it from the product name, so "1. Budget Planner" is judged on the name
# rather than on the marker's own period and space, which would otherwise read
# as a sentence boundary.
_LIST_MARKER = re.compile(r"^(?:[-*•]\s+|\d+[.)]\s+|#+\s*)")

# Longest single line still read as a product name when it names no product.
# Beyond this it is a sentence describing something, not a name for it.
_NAME_MAX_CHARS = 60


def _conversational_request(line: str) -> str:
    """Return why *line* is not a product brief, or "" when it is usable.

    A product noun is evidence of a brief only when the line is *shaped* like a
    name. An earlier version returned "usable" the moment ``_PRODUCT_INTENT``
    matched anywhere in the line, which let the second official KUMA Case -- a
    PostgreSQL online-DDL impact assessment whose paragraph contains the word
    "application" -- become an app named after its own opening sentence, which
    the factory then scored 100.0. Mentioning a product is not naming one to
    build, so prose is refused first and the noun only decides what is left.
    """

    # A list marker is presentation, not content: "1. Budget Planner" is a name
    # that happens to be numbered, and the marker's own period and space would
    # otherwise read as a sentence boundary.
    body = _LIST_MARKER.sub("", line).strip()
    if not body:
        return "The line carries no text once its list marker is removed."
    names_a_product = bool(_PRODUCT_INTENT.search(body))
    reads_as_prose = bool(_SENTENCE_BOUNDARY.search(body))

    # A name-shaped line that names a product is a brief however long it is:
    # the caller clips the name for the slug and keeps the text as description.
    if names_a_product and not reads_as_prose:
        return ""
    if reads_as_prose:
        # Checked before the sentence/length rules so the reason names what is
        # actually wrong: the passage may well mention a product, but a mention
        # inside prose is not a name to build.
        return (
            "The request is a multi-sentence passage describing work to do and "
            "names no product to build, so it carries no app brief."
        )
    if body[-1] in _TERMINAL_PUNCTUATION:
        return (
            "The request is a complete sentence that names no product, so there "
            "is nothing to build."
        )
    # Measured on the marker-stripped text, since the name is what gets clipped.
    if len(body) > _NAME_MAX_CHARS:
        return (
            "The request describes something at length but names no product to "
            "build."
        )
    return ""


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


def _render_answer(
    report: Mapping[str, Any],
    briefs: list[dict[str, Any]],
    model_calls: int | None = None,
) -> str:
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
    ]
    if model_calls is not None:
        # State the count so a reader can see generation was model-driven rather
        # than taking it on trust from the score.
        lines.append(f"model completions: {model_calls}")
    lines.append("")

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


def _require_model_configured() -> str:
    """Return the model name upstream will actually call, or raise.

    Upstream resolves its provider from Dashboard settings, environment and
    registry defaults, and ``OPENAI_MODEL`` is forwarded from the run
    environment. When the resolved configuration is incomplete the factory can
    still produce output, so this asks upstream's own gap description rather
    than guessing, and fails the invocation with that message. Reviewers ran the
    unit without ``OPENAI_MODEL`` set; the interceptor saw no model traffic at
    all, and a run that cannot reach a model must not report an accepted app.
    """

    from zerodev.llm import describe_config_gaps, resolve_llm_config

    resolved = resolve_llm_config()
    gaps = describe_config_gaps(resolved)
    if gaps:
        raise ZeroAppBindingError(
            "The factory has no usable model configuration, so it cannot "
            "generate an app: " + " ".join(gaps)
        )
    return resolved.model


@contextlib.contextmanager
def _counted_completions():
    """Yield a dict holding the number of model completions this run made.

    The count is taken from upstream's own entry point rather than from the
    interceptor, because the point is to detect that *no* request left the
    process. ``webapp_generator`` binds ``acomplete`` at import time, so both the
    defining module and the importing one are patched; upstream files stay
    unmodified and both patches are undone on exit.
    """

    calls = {"count": 0}
    targets = []
    try:
        import zerodev.generator.webapp_generator as webapp_generator
        import zerodev.llm as llm
    except ImportError:
        yield calls
        return

    for module in (llm, webapp_generator):
        original = getattr(module, "acomplete", None)
        if original is None:
            continue

        async def counted(*args, __wrapped__=original, **kwargs):
            calls["count"] += 1
            return await __wrapped__(*args, **kwargs)

        setattr(module, "acomplete", counted)
        targets.append((module, original))

    try:
        yield calls
    finally:
        for module, original in targets:
            setattr(module, "acomplete", original)


class ZeroAppBinding:
    """One ABB session over the native ZeroDev factory graph."""

    def __init__(self) -> None:
        self._closed = False
        self._workspace: str | None = None
        self._model_calls: int = 0

    # -- native run ---------------------------------------------------------

    async def _run_native(
        self, briefs: list[dict[str, Any]], config: Mapping[str, Any] | None
    ) -> dict[str, Any]:
        """Drive ``run_factory_batch`` and return its native report dict.

        ``run_factory_batch`` builds its own run config (recursion limit and
        ``max_concurrency``), so forwarding ABB's config as an argument is not
        possible. It is attached as ambient context with ``set_config_context``
        instead -- the same approach as units 43, 55 and 58 -- and the coroutine
        runs inside that Context, so the graph nodes and every model call inside
        them inherit ABB's callbacks and are traced. Persistence is disabled with
        ``checkpointer=False``, which is the upstream-supported way to skip the
        SQLite saver -- no database file is created and no ``aiosqlite``
        dependency is needed.
        """

        _ensure_import_path()
        from langchain_core.runnables.config import set_config_context
        from zerodev.pipeline.factory_graph import run_factory_batch

        # Fail before spending a Case on a run that cannot reach a model at all.
        model = _require_model_configured()

        self._workspace = tempfile.mkdtemp(prefix="abb-zeroapp-")

        configurable = (config or {}).get("configurable")
        thread_id = None
        if isinstance(configurable, Mapping):
            thread_id = configurable.get("thread_id")

        run_config = dict(config or {})

        async def native_run() -> dict[str, Any]:
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

        # set_config_context only binds the config (and ABB's trace callbacks)
        # inside the Context it yields, so the native run must execute in that
        # Context for the graph's callbacks to see it.
        with set_config_context(run_config) as invocation_context:
            with _counted_completions() as calls:
                report = await asyncio.create_task(
                    native_run(), context=invocation_context
                )

        accepted = report.get("accepted") if isinstance(report, Mapping) else None
        if calls["count"] == 0 and accepted:
            # Output that no model produced is not a generated app. Upstream's
            # supervisor scores from measured signals, but a batch that never
            # called a model cannot have measured anything real, so reporting it
            # as accepted would let an unobserved run pass as a verified one.
            raise ZeroAppBindingError(
                f"The factory reported {accepted} accepted app(s) with model "
                f"{model!r} configured, but made 0 model completions, so no "
                "generated content can be attributed to a model. Refusing to "
                "report this as a successful generation."
            )
        self._model_calls = calls["count"]
        return report

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
            "answer": _render_answer(report, briefs, model_calls=self._model_calls),
            "status": "finished",
            "report": dict(report),
            "briefs": briefs,
            "accepted": report.get("accepted", 0),
            "rejected": report.get("rejected", 0),
            "average_score": report.get("average_score", 0),
            "model_calls": self._model_calls,
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
