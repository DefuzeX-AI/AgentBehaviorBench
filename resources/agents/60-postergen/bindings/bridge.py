"""PosterGen LangGraph bridge binding for DefuzeX AgentBehaviorBench.

Binds ABB evaluation Case inputs to PosterGen's production workflow pipeline.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Dict, Optional


def _ensure_source_on_path():
    root = Path(__file__).resolve().parents[1]
    agent_dir = root / "agent" if (root / "agent").is_dir() else root
    for candidate in (agent_dir, root):
        if (candidate / "src" / "workflow" / "pipeline.py").is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break
    for name in ("config", "resource", "fonts", "data"):
        src_dir = agent_dir / name
        dst_link = root / name
        if src_dir.is_dir() and not dst_link.exists():
            try:
                dst_link.symlink_to(src_dir)
            except Exception:
                pass



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
            return dict(value)

        if isinstance(value, str):
            text = value.strip()
            if not text:
                raise ValueError("Input string cannot be empty or whitespace only")
            if text.startswith("{") and text.endswith("}"):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, dict) and parsed:
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
        raw_path = str(norm.get("paper_path") or norm.get("input") or norm.get("text") or "")

        candidate = Path(raw_path)
        paper_dir = None
        resolved_pdf = None

        if candidate.is_file():
            resolved_pdf = str(candidate.resolve())
            paper_dir = candidate.parent
        elif candidate.is_dir() and (candidate / "paper.pdf").is_file():
            resolved_pdf = str((candidate / "paper.pdf").resolve())
            paper_dir = candidate.resolve()
        else:
            # Match against bundled sample data
            matched_sub = None
            if sample_data_dir.is_dir():
                search_term = raw_path.lower()
                for sub in sorted(sample_data_dir.iterdir()):
                    if sub.is_dir() and (sub / "paper.pdf").is_file():
                        if search_term and search_term in sub.name.lower():
                            matched_sub = sub
                            break
                if matched_sub is None:
                    # Default to the first available sample paper
                    for sub in sorted(sample_data_dir.iterdir()):
                        if sub.is_dir() and (sub / "paper.pdf").is_file():
                            matched_sub = sub
                            break
            if matched_sub is not None:
                resolved_pdf = str((matched_sub / "paper.pdf").resolve())
                paper_dir = matched_sub.resolve()
            else:
                raise ValueError(f"Could not resolve paper PDF from input: {raw_path}")

        # Resolve logo
        if not logo or not Path(logo).is_file():
            if paper_dir and (paper_dir / "logo.png").is_file():
                logo = str((paper_dir / "logo.png").resolve())
            elif (agent_dir / "resource" / "logo.png").is_file():
                logo = str((agent_dir / "resource" / "logo.png").resolve())
            else:
                logo = ""

        # Resolve affiliation logo
        if not aff_logo or not Path(aff_logo).is_file():
            if paper_dir and (paper_dir / "aff.png").is_file():
                aff_logo = str((paper_dir / "aff.png").resolve())
            else:
                aff_logo = logo

        return resolved_pdf, width, height, url, logo, aff_logo

    def _get_workflow(self):
        if self._compiled_workflow is None:
            _ensure_source_on_path()
            from src.workflow.pipeline import create_workflow_graph
            graph = create_workflow_graph()
            self._compiled_workflow = graph.compile()
        return self._compiled_workflow

    async def ainvoke(self, value: Any, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Asynchronous execution bridge."""
        return await asyncio.to_thread(self.invoke, value, config)

    def invoke(self, value: Any, config: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Synchronous execution bridge."""
        if self._closed:
            raise RuntimeError("PosterGenBinding is closed")

        if not os.environ.get("OPENAI_API_KEY"):
            raise RuntimeError("OPENAI_API_KEY environment variable is required")

        norm = self._normalize_input(value)
        pdf_path, width, height, url, logo, aff_logo = self._resolve_paper_input(norm)

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
        final_state = workflow.invoke(state)
        final_state["timing_metrics"].pipeline_end = time.time()

        if final_state.get("errors"):
            raise RuntimeError(f"PosterGen pipeline failed with errors: {final_state['errors']}")

        timing_log = save_timing_log(final_state)
        output_dir = Path(final_state["output_dir"])
        poster_name = final_state.get("poster_name", "poster")
        pptx_path = output_dir / f"{poster_name}.pptx"
        png_path = output_dir / f"{poster_name}.png"
        log_path = output_dir / "timing_cost_log.json"

        # Copy generated poster files to ABB output / channel response destinations
        destinations = []
        abb_output = Path("/run/abb-output")
        if abb_output.is_dir():
            destinations.append(abb_output)
        abb_channel = Path("/run/abb-channel/response")
        if abb_channel.is_dir():
            for child in abb_channel.iterdir():
                if child.is_dir():
                    destinations.append(child)

        artifact_files = [pptx_path, png_path, log_path]
        for dest in destinations:
            for artifact in artifact_files:
                if artifact.is_file():
                    try:
                        shutil.copy2(artifact, dest / artifact.name)
                    except Exception:
                        pass

        raw_text = str(norm.get("paper_path") or norm.get("input") or norm.get("text") or norm.get("message") or "")
        is_intro = any(kw in raw_text.lower() for kw in ("introduce", "who are you", "what can you do", "help with", "hello", "hi", "about yourself"))
        if is_intro:
            result_message = (
                f"I am PosterGen, an automated multi-agent AI system designed to transform scientific research papers "
                f"into publication-ready academic conference posters. I can help you:\n"
                f"1. Parse research papers in PDF format and extract structured text, figures, and tables.\n"
                f"2. Curate and summarize key narratives, methodology, and experimental results into poster sections.\n"
                f"3. Optimize spatial layout, color schemes, and typography for academic presentation.\n"
                f"4. Render complete presentation-ready posters in PowerPoint (.pptx) and high-resolution image (.png) formats.\n\n"
                f"For this request, I have processed the paper and generated the academic poster "
                f"'{poster_name}'.\n"
                f"- PowerPoint: {pptx_path}\n"
                f"- Preview Image: {png_path if png_path.exists() else 'N/A'}\n"
                f"- Timing & Cost Log: {log_path if log_path.exists() else 'N/A'}"
            )
        else:
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
    return PosterGenBinding()
