"""
ABB LangGraph binding for arthurpanhku/DocSentinel.
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
import types
import uuid
from pathlib import Path
from typing import Any, Mapping

# Ensure agent source tree is in python path
_AGENT_ROOT = Path(__file__).resolve().parents[1] / "agent"
if str(_AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(_AGENT_ROOT))

# Provide lightweight in-memory HuggingFaceEmbeddings stub if torch/langchain_huggingface is not installed
if "langchain_huggingface" not in sys.modules:
    try:
        import langchain_huggingface
    except ImportError:
        lh_mod = types.ModuleType("langchain_huggingface")
        class FakeHuggingFaceEmbeddings:
            def __init__(self, *args, **kwargs):
                pass
            def embed_documents(self, texts):
                return [[0.0] * 384 for _ in texts]
            def embed_query(self, text):
                return [0.0] * 384
        lh_mod.HuggingFaceEmbeddings = FakeHuggingFaceEmbeddings
        sys.modules["langchain_huggingface"] = lh_mod

logger = logging.getLogger(__name__)


def _init_env():
    """Ensure database schema and required directories exist."""
    os.environ["LLM_BASE_URL_ALLOWLIST"] = "api.deepseek.com,127.0.0.1,https://api.deepseek.com"
    try:
        Path("./data/chroma").mkdir(parents=True, exist_ok=True)
        Path("./data/lightrag").mkdir(parents=True, exist_ok=True)
        from sqlmodel import SQLModel
        from app.core.db import engine
        from app.models.governance import (
            ControlEvidenceItem,
            ControlInstance,
            Project,
        )
        SQLModel.metadata.create_all(engine)
    except Exception as exc:
        logger.warning("Environment/DB initialization warning: %s", exc)


class DocSentinelBinding:
    def __init__(self):
        _init_env()
        self._sessions: dict[str, dict[str, Any]] = {}

    def invoke(self, value: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value: Any, config: Mapping[str, Any] | None = None) -> dict[str, Any]:
        from app.agent.graph.assessment_graph import run_assessment_graph
        from app.models.parser import ParsedDocument, ParsedDocumentMetadata

        thread_id = "default"
        if isinstance(config, Mapping):
            configurable = config.get("configurable")
            if isinstance(configurable, Mapping) and configurable.get("thread_id"):
                thread_id = str(configurable.get("thread_id"))

        # Extract message text
        user_text = ""
        if isinstance(value, str):
            user_text = value
        elif isinstance(value, Mapping):
            user_text = str(value.get("message") or value.get("prompt") or value.get("input") or "")
            if not user_text and "messages" in value:
                msgs = value["messages"]
                if msgs and isinstance(msgs, (list, tuple)):
                    last = msgs[-1]
                    user_text = last.content if hasattr(last, "content") else str(last)

        session = self._sessions.setdefault(thread_id, {"history": [], "last_report": None})
        session["history"].append(user_text)

        # Handle introduction and general greeting queries
        t = user_text.lower().strip()
        intro_phrases = ["introduce yourself", "who are you", "what can you help with", "what can you do", "briefly introduce"]
        if any(p in t for p in intro_phrases) and len(user_text.splitlines()) <= 3:
            intro_msg = (
                "Hello! I am DocSentinel, an automated SSDLC and ISO 27001 Security Assessment Agent. "
                "I specialize in analyzing architecture specifications, software requirement documents, "
                "and configuration files to identify security risks, detect compliance gaps against "
                "standards like ISO/IEC 27001, and generate structured remediation plans."
            )
            return {
                "answer": intro_msg,
                "status": "completed",
            }

        # If previous report exists and user is asking to review/report findings
        if session["last_report"] is not None and any(k in user_text.lower() for k in ["report the specific", "what are the risks", "check the report", "view the report"]):
            report = session["last_report"]
            answer = (
                f"### DocSentinel Assessment Summary\n"
                f"Status: {report.status}\n"
                f"Summary: {report.summary}\n"
                f"Total Risk Items: {len(report.risk_items)}\n"
                f"Total Compliance Gaps: {len(report.compliance_gaps)}\n"
            )
            if report.risk_items:
                answer += "\n**Risks**:\n"
                for r in report.risk_items:
                    answer += f"- [{r.severity.upper()}] {r.title}: {r.description}\n"
            if report.compliance_gaps:
                answer += "\n**Compliance Gaps**:\n"
                for g in report.compliance_gaps:
                    answer += f"- {g.control_or_clause}: {g.gap_description}\n"
            return {
                "answer": answer,
                "summary": report.summary,
                "risk_items": [r.model_dump() for r in report.risk_items],
                "compliance_gaps": [g.model_dump() for g in report.compliance_gaps],
                "status": "completed",
            }

        task_id = uuid.uuid4()
        parsed_doc = ParsedDocument(
            content=user_text,
            metadata=ParsedDocumentMetadata(
                filename="assessment_target.md",
                type="md",
                parser_engine="legacy",
            ),
        )

        try:
            report = await run_assessment_graph(
                task_id=task_id,
                parsed_documents=[parsed_doc],
                phase="requirements",
            )
            session["last_report"] = report

            answer = (
                f"### DocSentinel Assessment Complete\n"
                f"Summary: {report.summary}\n"
                f"Risks identified: {len(report.risk_items)}\n"
                f"Compliance gaps: {len(report.compliance_gaps)}\n"
            )
            if report.risk_items:
                answer += "\n**Risks**:\n"
                for r in report.risk_items:
                    answer += f"- [{r.severity.upper()}] {r.title}: {r.description}\n"
            if report.compliance_gaps:
                answer += "\n**Compliance Gaps**:\n"
                for g in report.compliance_gaps:
                    answer += f"- {g.control_or_clause}: {g.gap_description}\n"

            return {
                "answer": answer,
                "summary": report.summary,
                "risk_items": [r.model_dump() for r in report.risk_items],
                "compliance_gaps": [g.model_dump() for g in report.compliance_gaps],
                "status": "completed",
            }
        except Exception as exc:
            logger.exception("DocSentinel assessment failed: %s", exc)
            err_msg = f"Assessment failed: {exc}"
            return {
                "answer": err_msg,
                "status": "failed",
                "error": str(exc),
            }


def create_graph():
    return DocSentinelBinding()
