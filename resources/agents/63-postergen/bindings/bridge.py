"""PosterGen LangGraph bridge binding for DefuzeX AgentBehaviorBench.

Binds ABB evaluation Case inputs to PosterGen's production workflow pipeline.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import shutil
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, Optional, Union

logger = logging.getLogger("postergen.bridge")
if not logger.handlers:
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("[%(asctime)s] [%(name)s] [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

CONVERSATIONAL_PATTERNS = [
    # 1. Greetings & Salutations
    r"\b(?:hello|hi|hey|howdy|greetings|salutations)\b",
    r"\bgood\s+(?:morning|afternoon|evening|day)\b",
    r"\bhow\s+are\s+you\b",
    r"\bhow\s+do\s+you\s+do\b",
    r"\bhow'?s\s+it\s+going\b",
    r"\bnice\s+to\s+meet\s+you\b",

    # 2. Self-Introduction & Identity Inquiries
    r"\bintroduce\s+yourself\b",
    r"\bintroduce\s+(?:the\s+)?(?:agent|tool|postergen|system)\b",
    r"\bself[- ]introduction\b",
    r"\b(?:give\s+me\s+an\s+)?introduction\s+to\s+(?:postergen|this\s+agent|this\s+tool|the\s+system)\b",
    r"\bwho\s+are\s+you\b",
    r"\bwho\s+is\s+(?:this|the)?\s*agent\b",
    r"\bwhat\s+are\s+you\b",
    r"\bwhat\s+is\s+(?:this|the)?\s*(?:agent|tool|system|service|postergen)\b",
    r"\bwhat\s+is\s+this\b",
    r"\babout\s+yourself\b",
    r"\btell\s+me\s+about\s+yourself\b",
    r"\bdescribe\s+yourself\b",
    r"\bexplain\s+yourself\b",
    r"\bwho\s+made\s+you\b",
    r"\bwhat\s+kind\s+of\s+agent\b",

    # 3. Capabilities, Functionality & Feature Inquiries
    r"\bcapable\b",
    r"\bcapabilities\b",
    r"\bcapability\b",
    r"\bfunctionality\b",
    r"\b(?:what\s+are\s+the\s+)?features\s+of\s+(?:postergen|this\s+agent|this\s+tool|the\s+system)\b",
    r"\bwhat\s+(?:features|capabilities|functions)\s+(?:do|does)\s+(?:you|postergen|(?:this|the)\s+(?:agent|tool|system))\s+have\b",
    r"\bwhat\s+are\s+(?:the|your)\s+(?:features|functions)\b",
    r"\bfunctions\s+of\s+(?:postergen|this\s+agent|this\s+tool|the\s+system)\b",
    r"\bwhat\s+(?:can|does|do)\s+(?:[\w\-]+\s+){0,2}do\b",
    r"\bwhat\s+(?:you|this\s+\w+)\s+(?:can\s+)?do\b",
    r"\bwhat\s+can\s+i\s+do\b",
    r"\bcan\s+you\s+describe\b",
    r"\bwhat\s+is\s+your\s+(?:purpose|role|function|mission)\b",
    r"\bwhat\s+are\s+your\s+(?:purpose|role|functions|features|capabilities)\b",

    # 4. Usage, Instructions, How-It-Works & Help Inquiries
    r"\bhow\s+(?:does|do)\s+(?:[\w\-]+\s+){0,2}work\b",
    r"\bhow\s+this\s+works?\b",
    r"\bhow\s+it\s+works?\b",
    r"\bhow\s+to\s+use\b",
    r"\bhow\s+(?:do|can)\s+i\s+use\b",
    r"\bhelp\b",
    r"\binstructions\b",
    r"\buser\s+guide\b",
    r"\bquickstart\b",
    r"\boverview\b",
]
CONVERSATIONAL_REGEX = re.compile("|".join(CONVERSATIONAL_PATTERNS), re.IGNORECASE)

IMPERATIVE_POSTER_REGEX = re.compile(
    r"\b(?:generate|make|create|build|render|produce|synthesize|design)\s+(?:a\s+|an\s+)?poster\b",
    re.IGNORECASE
)

POSTERGEN_CAPABILITIES_TEXT = (
    "I am PosterGen, an automated multi-agent AI system designed to transform scientific research papers "
    "into publication-ready academic conference posters. I coordinate specialized agents built on LangGraph to:\n"
    "1. Parse research papers in PDF format and extract structured text, figures, and tables (via Marker/Surya).\n"
    "2. Curate and summarize key narratives, methodology, and experimental results into structured poster sections.\n"
    "3. Optimize spatial layout, color schemes, and typography tailored for academic presentation.\n"
    "4. Render complete presentation-ready posters in PowerPoint (.pptx) and high-resolution image (.png) formats.\n\n"
    "To generate an academic poster, please provide an accessible research paper in PDF format "
    "(e.g. specify 'paper_path' pointing to a valid .pdf file)."
)


def _ensure_source_on_path():
    root = Path(__file__).resolve().parents[1]
    agent_dir = root / "agent" if (root / "agent").is_dir() else root
    for candidate in (agent_dir, root):
        if (candidate / "src" / "workflow" / "pipeline.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break


def _configure_marker_runtime():
    """Configures Marker runtime settings for ABB in-process container stability.

    ABB runs agents inside an in-process container channel with background asyncio loops
    and active threads. Marker's PdfProvider by default sets pdftext_workers=4, which invokes
    ProcessPoolExecutor (multiprocessing.fork). In a multi-threaded process, forking child
    workers causes worker deadlocks in futex_wait_queue.
    Setting PdfProvider.pdftext_workers=1 enforces single-process in-line PDF text extraction,
    completely eliminating child worker forks and deadlocks without altering upstream code snapshots.
    This is an ABB in-process container compatibility requirement, not a performance tuning.
    """
    try:
        from marker.providers.pdf import PdfProvider
        PdfProvider.pdftext_workers = 1
        logger.info("Configured Marker PdfProvider.pdftext_workers = 1 for in-process container stability")
    except (ImportError, AttributeError) as exc:
        logger.debug("Marker PdfProvider not available for runtime configuration: %s", exc)


def _configure_color_agent_runtime():
    """Configures ColorAgent runtime settings for text-only model environments.

    In ABB evaluation benchmarks, model interception routes often default to text-only
    generation endpoints (e.g. DeepSeek, GLM, or environments without a dedicated vision lane).
    ColorAgent in PosterGen originally invokes a vision LLM to extract theme colors from logo/figures.
    When no vision target lane exists, this causes a request_preparation_failed interceptor error.
    This helper applies direct PIL-based dominant color extraction when running under text-only
    providers (or when ABB_ENABLE_VISION_LLM is not explicitly enabled), eliminating the vision
    lane dependency while reliably extracting authentic brand colors in < 5ms.
    """
    try:
        from PIL import Image
        from src.agents.color_agent import ColorAgent

        def _extract_dominant_color_pil(image_path: str) -> str:
            try:
                if not image_path or not Path(image_path).exists():
                    return "#1E3A8A"
                with Image.open(image_path) as img:
                    img = img.convert("RGBA").resize((100, 100))
                    colors = img.getcolors(maxcolors=10000)
                    if not colors:
                        return "#1E3A8A"
                    candidates = []
                    for count, (r, g, b, a) in colors:
                        if a < 128:
                            continue
                        brightness = (r * 299 + g * 587 + b * 114) / 1000
                        max_c = max(r, g, b)
                        min_c = min(r, g, b)
                        sat = (max_c - min_c) / max_c if max_c > 0 else 0
                        if 40 < brightness < 220 and sat > 0.15:
                            candidates.append((count * sat, (r, g, b)))
                    if candidates:
                        candidates.sort(reverse=True)
                        r, g, b = candidates[0][1]
                        return f"#{r:02x}{g:02x}{b:02x}"
            except Exception:
                pass
            return "#1E3A8A"

        orig_extract_logo = ColorAgent._extract_theme_from_logo

        def safe_extract_theme_from_logo(self, logo_path: str, state):
            provider = os.environ.get("ABB_MODEL_PROVIDER", "").lower()
            has_deepseek = bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_MODEL"))
            enable_vision = os.environ.get("ABB_ENABLE_VISION_LLM", "0") == "1"
            if not enable_vision or provider in ("deepseek", "glm") or has_deepseek:
                color = _extract_dominant_color_pil(logo_path)
                logger.info("Extracted logo theme color via direct PIL analyzer: %s", color)
                return color
            try:
                return orig_extract_logo(self, logo_path, state)
            except Exception as exc:
                logger.warning("Vision logo extraction failed (%s); falling back to direct PIL analyzer", exc)
                return _extract_dominant_color_pil(logo_path)

        orig_extract_visuals = ColorAgent._extract_theme_from_visuals

        def safe_extract_theme_from_visuals(self, state):
            provider = os.environ.get("ABB_MODEL_PROVIDER", "").lower()
            has_deepseek = bool(os.environ.get("DEEPSEEK_API_KEY") or os.environ.get("DEEPSEEK_MODEL"))
            enable_vision = os.environ.get("ABB_ENABLE_VISION_LLM", "0") == "1"
            if not enable_vision or provider in ("deepseek", "glm") or has_deepseek:
                classified = state.get("classified_visuals", {})
                key_visual = classified.get("key_visual")
                images = state.get("images", {})
                if key_visual and key_visual.startswith("figure_"):
                    fig_id = key_visual.replace("figure_", "")
                    if fig_id in images and images[fig_id].get("path"):
                        return _extract_dominant_color_pil(images[fig_id]["path"])
                return "#1E3A8A"
            try:
                return orig_extract_visuals(self, state)
            except Exception as exc:
                logger.warning("Vision visual extraction failed (%s); falling back to direct PIL analyzer", exc)
                return "#1E3A8A"

        ColorAgent._extract_theme_from_logo = safe_extract_theme_from_logo
        ColorAgent._extract_theme_from_visuals = safe_extract_theme_from_visuals
        logger.info("Configured ColorAgent runtime with safe direct PIL fallback")
    except (ImportError, AttributeError) as exc:
        logger.debug("ColorAgent not available for runtime configuration: %s", exc)


def _is_safe_path_candidate(path_obj: Union[str, Path, None]) -> bool:
    """Validates whether path_obj can safely be tested against filesystem without OSError [Errno 36]."""
    if not path_obj:
        return False
    try:
        raw = os.fspath(path_obj)
        if not raw or "\0" in raw:
            return False
        raw_bytes = os.fsencode(raw)
        # POSIX PATH_MAX limit (4096 bytes)
        if len(raw_bytes) > 4096:
            return False
        # POSIX NAME_MAX limit per component (255 bytes)
        components = raw_bytes.split(b"/")
        if any(len(c) > 255 for c in components):
            return False
        return True
    except (OSError, ValueError, TypeError):
        return False


def _safe_exists(target: Union[str, Path, None]) -> bool:
    """Safely checks if target exists, catching all OSErrors, ValueErrors, and length violations."""
    if not _is_safe_path_candidate(target):
        return False
    try:
        return os.path.exists(target)
    except (OSError, ValueError, TypeError):
        return False


def _safe_is_file(target: Union[str, Path, None]) -> bool:
    """Safely checks if target is a regular file, catching all OSErrors and length violations."""
    if not _is_safe_path_candidate(target):
        return False
    try:
        return os.path.isfile(target)
    except (OSError, ValueError, TypeError):
        return False


def _safe_is_dir(target: Union[str, Path, None]) -> bool:
    """Safely checks if target is a directory, catching all OSErrors and length violations."""
    if not _is_safe_path_candidate(target):
        return False
    try:
        return os.path.isdir(target)
    except (OSError, ValueError, TypeError):
        return False


def _validate_pdf_file(target: Path, display_name: str) -> None:
    """Validate that a candidate is a readable, structurally parseable PDF."""
    try:
        size = target.stat().st_size
        if size == 0:
            raise ValueError(f"Provided paper PDF '{display_name}' is empty (0 bytes).")

        with target.open("rb") as stream:
            header = stream.read(8)
            if not header.startswith(b"%PDF-"):
                raise ValueError(
                    f"Provided paper file '{display_name}' does not have a valid PDF header."
                )
            stream.seek(max(0, size - 4096))
            trailer = stream.read()
            if b"%%EOF" not in trailer:
                raise ValueError(
                    f"Provided paper PDF '{display_name}' is truncated or missing its PDF trailer."
                )
    except OSError as exc:
        raise ValueError(f"Could not read research paper PDF '{display_name}': {exc}") from exc

    # PosterGen declares pypdf as a runtime dependency. Use it when materialized
    # to reject malformed cross-reference tables and page trees before loading
    # Marker's expensive OCR models. The lightweight host-side contract tests do
    # not install the Agent dependency set, so the structural checks above remain
    # the deterministic fallback there.
    try:
        from pypdf import PdfReader
    except ImportError:
        return

    try:
        reader = PdfReader(str(target), strict=False)
        if len(reader.pages) == 0:
            raise ValueError("the document contains no pages")
        # Force the first page tree and media box to be resolved instead of only
        # accepting a superficially valid trailer.
        _ = reader.pages[0].mediabox
    except Exception as exc:
        raise ValueError(
            f"Provided paper PDF '{display_name}' could not be parsed: {exc}"
        ) from exc


class PosterGenBinding:
    """Encapsulates PosterGen's compiled StateGraph and per-case execution."""

    def __init__(self):
        _ensure_source_on_path()
        self._compiled_workflow = None
        self._closed = False

    def _normalize_input(self, value: Any) -> Dict[str, Any]:
        """Normalizes input into a structured mapping, rejecting invalid inputs."""
        if value is None:
            raise ValueError("Input value cannot be None")

        if isinstance(value, Mapping):
            if not value:
                raise ValueError("Input mapping cannot be empty")
            d = dict(value)
            if "paper_path" in value:
                d["_explicit_paper_path"] = True
            return d

        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("Input string cannot be empty or whitespace only")
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and parsed:
                        if "paper_path" in parsed:
                            parsed["_explicit_paper_path"] = True
                        return parsed
                except Exception:
                    pass
            return {
                "paper_path": text,
                "text": text,
                "message": text,
                "topic": text,
            }

        raise ValueError(f"Unsupported input type: {type(value)}")

    def _extract_text_and_candidate(self, norm: Dict[str, Any]) -> tuple[str, str]:
        """Extracts text content and raw paper candidate path from normalized input."""
        explicit_paper = str(norm.get("paper_path") or "").strip()
        msg_text = ""
        messages = norm.get("messages")
        if isinstance(messages, list) and messages:
            last = messages[-1]
            if isinstance(last, dict) and "content" in last:
                msg_text = str(last["content"]).strip()
            elif hasattr(last, "content"):
                msg_text = str(getattr(last, "content")).strip()

        raw_text = str(
            msg_text
            or norm.get("text")
            or norm.get("message")
            or norm.get("input")
            or norm.get("prompt")
            or norm.get("query")
            or explicit_paper
            or ""
        ).strip()

        candidate = explicit_paper or raw_text
        return raw_text, candidate

    def _is_conversational_request(
        self,
        raw_text: str,
        candidate: str,
        norm: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Determines if the request is conversational without valid paper references."""
        if not raw_text:
            return False

        # 1. If paper_path is explicitly provided in an input dictionary, return False immediately
        if norm is not None and (
            norm.get("_explicit_paper_path")
            or (norm.get("paper_path") and norm.get("paper_path") != raw_text)
        ):
            return False

        cand_clean = candidate.strip().strip("'\"")

        # 2. Existing file or directory on filesystem is a paper input (valid or invalid), never conversational
        if cand_clean and _safe_exists(cand_clean):
            return False

        # 3. Embedded or explicit .pdf reference in raw_text or candidate indicates a paper request
        combined_text = f"{raw_text} {candidate}"
        if re.search(r'[\w\-./\\]+\.pdf\b', combined_text, re.IGNORECASE):
            return False

        # 4. Poster generation actions/intent alongside or within a paper request
        if IMPERATIVE_POSTER_REGEX.search(raw_text):
            return False

        # 5. Path-like candidate with non-PDF file extension indicates an invalid paper input attempt
        if _is_safe_path_candidate(cand_clean):
            cand_path = Path(cand_clean)
            cand_ext = cand_path.suffix.lower()
            is_valid_ext = bool(re.match(r"^\.[a-zA-Z0-9]{1,10}$", cand_ext))
            non_pdf_exts = {
                ".txt", ".docx", ".doc", ".png", ".jpg", ".jpeg",
                ".tex", ".md", ".zip", ".tar", ".gz", ".csv", ".json",
            }
            if cand_ext in non_pdf_exts:
                return False
            if ("/" in cand_clean or "\\" in cand_clean) and is_valid_ext:
                return False

        # 6. Explicit bundled sample data reference indicates a paper request
        root = Path(__file__).resolve().parents[1]
        agent_dir = root / "agent" if (root / "agent").is_dir() else root
        sample_data_dir = agent_dir / "data"
        if _safe_is_dir(sample_data_dir) and cand_clean:
            cand_path = Path(cand_clean) if _is_safe_path_candidate(cand_clean) else None
            clean_name = cand_path.name.lower() if cand_path else ""
            parent_name = cand_path.parent.name.lower() if cand_path else ""
            for sub in sample_data_dir.iterdir():
                if sub.is_dir() and (sub / "paper.pdf").is_file():
                    sub_name_lower = sub.name.lower()
                    if (
                        (clean_name and clean_name == sub_name_lower)
                        or (parent_name and parent_name == sub_name_lower)
                        or cand_clean.lower() == sub_name_lower
                        or sub_name_lower in raw_text.lower()
                    ):
                        return False

        # 7. Evaluate conversational patterns
        return bool(CONVERSATIONAL_REGEX.search(raw_text))

    def _resolve_paper_input(self, norm: Dict[str, Any]) -> tuple[str, float, float, str, str, str]:
        """Resolves input into (pdf_path, width, height, url, logo, aff_logo)."""
        root = Path(__file__).resolve().parents[1]
        agent_dir = root / "agent" if (root / "agent").is_dir() else root
        sample_data_dir = agent_dir / "data"

        width = float(norm.get("poster_width", 54.0))
        height = float(norm.get("poster_height", 36.0))
        if height <= 0:
            height = 36.0
        ratio = width / height
        if ratio < 1.4 or ratio > 2.0:
            width = 54.0
            height = 36.0

        url = str(norm.get("url", ""))
        logo = str(norm.get("logo", ""))
        aff_logo = str(norm.get("aff_logo", ""))

        raw_text, raw_path = self._extract_text_and_candidate(norm)
        raw_path = raw_path.strip().strip("'\"")

        if not raw_path:
            raise ValueError("No research paper input specified. Please provide a path to a PDF file.")

        # If raw_path is free-form text, look for an embedded .pdf path
        sample_cand = sample_data_dir / raw_path if _is_safe_path_candidate(raw_path) else None
        if not _safe_exists(raw_path) and not _safe_is_dir(sample_cand):
            pdf_match = re.search(r'([^\s"\'<>*|?]+\.pdf)\b', raw_path, re.IGNORECASE)
            if pdf_match:
                raw_path = pdf_match.group(1).strip().strip("'\"")

        # Resolve candidate path: direct, or relative to sample_data_dir, agent_dir, or parent
        candidate = None
        if _is_safe_path_candidate(raw_path):
            p = Path(raw_path)
            if _safe_exists(p):
                candidate = p
            elif _safe_exists(sample_data_dir / p):
                candidate = sample_data_dir / p
            elif _safe_exists(agent_dir / p):
                candidate = agent_dir / p
            elif _safe_exists(sample_data_dir.parent / p):
                candidate = sample_data_dir.parent / p
            else:
                candidate = p

        paper_dir = None
        resolved_pdf = None

        if candidate and _safe_is_file(candidate):
            if candidate.suffix.lower() != ".pdf":
                raise ValueError(
                    f"Provided paper file '{raw_path}' is not a PDF file. "
                    f"PosterGen requires research paper manuscripts in PDF format (.pdf)."
                )
            _validate_pdf_file(candidate, raw_path)
            resolved_pdf = str(candidate.resolve())
            paper_dir = candidate.parent
        elif candidate and _safe_is_dir(candidate):
            pdf_file = candidate / "paper.pdf"
            if not _safe_is_file(pdf_file):
                raise ValueError(f"Directory '{raw_path}' does not contain 'paper.pdf'.")
            _validate_pdf_file(pdf_file, str(pdf_file))
            resolved_pdf = str(pdf_file.resolve())
            paper_dir = candidate.resolve()
        else:
            # Match against bundled sample data by explicit folder name or embedded folder reference
            matched_sub = None
            if _safe_is_dir(sample_data_dir):
                clean_name = candidate.name.lower() if (candidate and _is_safe_path_candidate(candidate)) else ""
                parent_name = candidate.parent.name.lower() if (candidate and _is_safe_path_candidate(candidate)) else ""
                for sub in sorted(sample_data_dir.iterdir()):
                    if sub.is_dir() and (sub / "paper.pdf").is_file():
                        sub_name_lower = sub.name.lower()
                        if (
                            (clean_name and clean_name == sub_name_lower)
                            or (parent_name and parent_name == sub_name_lower)
                            or (raw_path and raw_path.lower() == sub_name_lower)
                            or (len(sub_name_lower) >= 10 and sub_name_lower in raw_text.lower())
                        ):
                            matched_sub = sub
                            break

            if matched_sub is not None:
                pdf_file = matched_sub / "paper.pdf"
                _validate_pdf_file(pdf_file, str(pdf_file))
                resolved_pdf = str(pdf_file.resolve())
                paper_dir = matched_sub.resolve()
            else:
                display_path = (raw_path[:120] + "...") if len(raw_path) > 120 else raw_path
                raise ValueError(
                    f"Could not resolve research paper PDF from input: '{display_path}'. "
                    f"The specified path does not exist or is not a recognized paper manuscript."
                )

        # Resolve logo
        if not logo or not _safe_is_file(logo):
            if paper_dir and (paper_dir / "logo.png").is_file():
                logo = str((paper_dir / "logo.png").resolve())
            elif (agent_dir / "resource" / "logo.png").is_file():
                logo = str((agent_dir / "resource" / "logo.png").resolve())
            else:
                logo = ""

        # Resolve affiliation logo
        if not aff_logo or not _safe_is_file(aff_logo):
            if paper_dir and (paper_dir / "aff.png").is_file():
                aff_logo = str((paper_dir / "aff.png").resolve())
            else:
                aff_logo = logo

        return resolved_pdf, width, height, url, logo, aff_logo

    def _get_destinations(self) -> list[Path]:
        destinations = []
        abb_output = Path("/run/abb-output")
        if abb_output.is_dir():
            destinations.append(abb_output)
        abb_channel = Path("/run/abb-channel/response")
        if abb_channel.is_dir():
            try:
                for child in sorted(abb_channel.iterdir()):
                    if child.is_dir():
                        destinations.append(child)
            except Exception as exc:
                logger.error("Failed to list channel response directories in %s: %s", abb_channel, exc)
        return destinations

    def _deliver_artifacts(self, artifact_files: list[Path], destinations: list[Path]) -> list[str]:
        delivery_errors = []
        for dest in destinations:
            for artifact in artifact_files:
                if artifact.is_file():
                    target = dest / artifact.name
                    try:
                        shutil.copy2(artifact, target)
                        logger.info("Successfully delivered artifact %s to %s", artifact.name, target)
                    except Exception as exc:
                        err_msg = f"Failed to deliver artifact '{artifact.name}' to '{target}': {type(exc).__name__}: {exc}"
                        logger.error(err_msg, exc_info=True)
                        delivery_errors.append(err_msg)

        if delivery_errors and destinations:
            raise RuntimeError(f"Artifact delivery failed for one or more files: {'; '.join(delivery_errors)}")
        return delivery_errors

    def _get_workflow(self):
        if self._compiled_workflow is None:
            _ensure_source_on_path()
            _configure_marker_runtime()
            _configure_color_agent_runtime()
            from src.workflow.pipeline import create_workflow_graph
            graph = create_workflow_graph()
            self._compiled_workflow = graph.compile()
        return self._compiled_workflow

    async def ainvoke(
        self,
        value: Any,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Asynchronous execution bridge."""
        if config is None and "run_config" in kwargs:
            config = kwargs.pop("run_config")
        return await asyncio.to_thread(self.invoke, value, config, **kwargs)

    def invoke(
        self,
        value: Any,
        config: Optional[Dict[str, Any]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Synchronous execution bridge."""
        if config is None and "run_config" in kwargs:
            config = kwargs.pop("run_config")

        if self._closed:
            raise RuntimeError("PosterGenBinding is closed")

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY environment variable is required")

        norm = self._normalize_input(value)
        raw_text, candidate = self._extract_text_and_candidate(norm)

        # 1. Fast conversational / introductory response without invoking pipeline
        if self._is_conversational_request(raw_text, candidate, norm=norm):
            logger.info("Handling conversational / introductory request without poster synthesis")
            return {
                "final_output": {
                    "answer": POSTERGEN_CAPABILITIES_TEXT,
                    "poster_name": None,
                    "pptx_path": None,
                    "png_path": None,
                    "artifacts": [],
                    "status": "completed",
                },
                "answer": POSTERGEN_CAPABILITIES_TEXT,
                "poster_name": None,
                "pptx_path": None,
                "png_path": None,
                "artifacts": [],
                "status": "completed",
            }

        # 2. Paper input resolution with clear diagnostic error per requirement.md
        try:
            pdf_path, width, height, url, logo, aff_logo = self._resolve_paper_input(norm)
        except (ValueError, FileNotFoundError, OSError) as err:
            diagnostic_msg = (
                f"Error: Unable to generate poster. Invalid or missing paper input: {err}\n"
                f"Requirement: PosterGen requires a valid, accessible research paper in PDF format (.pdf) "
                f"to perform content extraction and poster synthesis. No unrequested sample synthesis was executed."
            )
            logger.warning("Paper resolution failed: %s", err)
            return {
                "final_output": {
                    "answer": diagnostic_msg,
                    "error": str(err),
                    "poster_name": None,
                    "pptx_path": None,
                    "png_path": None,
                    "artifacts": [],
                    "status": "error",
                },
                "answer": diagnostic_msg,
                "error": str(err),
                "poster_name": None,
                "pptx_path": None,
                "png_path": None,
                "artifacts": [],
                "status": "error",
            }

        # 3. Poster generation pipeline execution
        _ensure_source_on_path()
        from src.state.poster_state import create_state
        from src.workflow.pipeline import save_timing_log

        state = create_state(
            pdf_path=pdf_path,
            text_model="gpt-4o-2024-08-06",
            vision_model="gpt-4o-2024-08-06",
            width=int(width),
            height=int(height),
            url=url,
            logo_path=logo,
            aff_logo_path=aff_logo,
        )

        state["timing_metrics"].pipeline_start = time.time()
        workflow = self._get_workflow()
        final_state = workflow.invoke(state, config=config)
        final_state["timing_metrics"].pipeline_end = time.time()

        if final_state.get("errors"):
            raise RuntimeError(f"PosterGen pipeline failed with errors: {final_state['errors']}")

        timing_log = save_timing_log(final_state)
        output_dir = Path(final_state["output_dir"])
        poster_name = final_state.get("poster_name", "poster")
        pptx_path = output_dir / f"{poster_name}.pptx"
        png_path = output_dir / f"{poster_name}.png"
        log_path = output_dir / "timing_cost_log.json"

        # Deliver generated poster files to ABB output / channel response destinations
        destinations = self._get_destinations()
        artifact_files = [pptx_path, png_path, log_path]
        self._deliver_artifacts(artifact_files, destinations)

        result_message = (
            f"Successfully generated poster '{poster_name}' in PowerPoint format: {pptx_path}. "
            f"Preview image: {png_path if png_path.exists() else 'N/A'}."
        )

        captured_artifacts = [p.name for p in artifact_files if p.exists()]

        return {
            "final_output": {
                "answer": result_message,
                "poster_name": poster_name,
                "pptx_path": str(pptx_path),
                "png_path": str(png_path) if png_path.exists() else None,
                "artifacts": captured_artifacts,
                "status": "completed",
            },
            "answer": result_message,
            "poster_name": poster_name,
            "pptx_path": str(pptx_path),
            "png_path": str(png_path) if png_path.exists() else None,
            "artifacts": captured_artifacts,
            "status": "completed",
            "timing_metrics": {
                "total_time": final_state["timing_metrics"].get_total_time(),
                "api_calls": final_state["timing_metrics"].get_api_call_count(),
            },
        }

    def close(self):
        self._compiled_workflow = None
        self._closed = True

    async def aclose(self):
        self.close()


def create_graph() -> PosterGenBinding:
    """Factory function returning a new PosterGenBinding instance."""
    _configure_marker_runtime()
    _configure_color_agent_runtime()
    return PosterGenBinding()
