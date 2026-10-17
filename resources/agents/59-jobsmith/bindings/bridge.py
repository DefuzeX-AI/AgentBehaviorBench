"""ABB binding for kevin333353/jobsmith.

Upstream entrypoint (source under ``agent/`` is unchanged):

* ``app/graph.py:build_graph`` compiles the progressive application-package
  LangGraph (parse → match → optional docs → human gate).
* Native UI/CLI defaults to Claude/Codex CLI backends; this deployment forces the
  OpenAI-compatible BYOK backend so ABB can intercept model traffic.

Deployment boundary:

* No job-board scraping, Tavily, desktop UI, or interactive human gate.
* Case input supplies one job description plus a candidate profile.
* ``batch=True`` skips ``interrupt()``; company research and AI critic are off;
  only a cover letter is requested to keep the Case bounded.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path
from typing import Any


_SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"


def _configure_openai_backend() -> None:
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for ABB model interception")
    os.environ["LLM_BACKEND"] = "openai"
    os.environ.setdefault(
        "OPENAI_BASE_URL",
        os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    os.environ.setdefault(
        "OPENAI_MODEL",
        os.environ.get("OPENAI_MODEL", "deepseek-v4-pro"),
    )
    # Avoid interactive checkpoint files in the container.
    os.environ["COPILOT_DB"] = ":memory:"


def _parse_case_input(value: Any) -> tuple[str, dict[str, Any]]:
    """Return (jd_text, profile_fields) from text or JSON Case input."""

    if isinstance(value, dict):
        payload = dict(value)
    elif isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("Jobsmith Case input must be a non-empty string or object.")
        try:
            loaded = json.loads(text)
            payload = loaded if isinstance(loaded, dict) else {"jd_text": text}
        except json.JSONDecodeError:
            payload = {"jd_text": text}
            # Optional "---" separator: JD above, profile below.
            if "\n---\n" in text:
                jd, profile_raw = text.split("\n---\n", 1)
                payload = {"jd_text": jd.strip(), "profile_text": profile_raw.strip()}
    else:
        raise ValueError("Case input must be a string or JSON object.")

    jd = str(
        payload.get("jd_text")
        or payload.get("job_description")
        or payload.get("jd")
        or ""
    ).strip()
    if not jd:
        raise ValueError("Case input must include a job description (jd_text).")

    profile = {
        "name": str(payload.get("name") or "Candidate"),
        "summary": str(payload.get("summary") or ""),
        "skills": payload.get("skills") or [],
        "experiences": payload.get("experiences") or [],
        "education": str(payload.get("education") or ""),
        "raw_text": str(payload.get("profile_text") or payload.get("resume") or ""),
        "preferred_roles": payload.get("preferred_roles") or [],
    }
    if isinstance(profile["skills"], str):
        profile["skills"] = [s.strip() for s in re.split(r"[,、/|]", profile["skills"]) if s.strip()]
    if isinstance(profile["experiences"], str):
        profile["experiences"] = [profile["experiences"]]
    if not profile["raw_text"]:
        bits = [
            profile["name"],
            profile["summary"],
            "Skills: " + ", ".join(profile["skills"]),
            "Experience: " + "; ".join(profile["experiences"]),
            profile["education"],
        ]
        profile["raw_text"] = "\n".join(b for b in bits if b and b != "Skills: " and b != "Experience: ")
    if not profile["summary"]:
        profile["summary"] = "Software engineer seeking a relevant role."
    if not profile["skills"]:
        profile["skills"] = ["Python", "LangGraph"]
    if not profile["experiences"]:
        profile["experiences"] = ["Built LLM application workflows in Python."]
    return jd, profile


class JobsmithBinding:
    def __init__(self):
        self._closed = False
        self._app = None

    def _ensure_app(self):
        if self._app is not None:
            return self._app
        if not _SOURCE_ROOT.is_dir():
            raise RuntimeError(f"Imported Agent source not found at {_SOURCE_ROOT}")

        _configure_openai_backend()
        os.chdir(_SOURCE_ROOT)
        if str(_SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(_SOURCE_ROOT))

        from langgraph.checkpoint.memory import MemorySaver

        import app.settings as settings

        settings._byok["api_key"] = os.environ.get("OPENAI_API_KEY", "")
        settings._byok["base_url"] = os.environ.get("OPENAI_BASE_URL", "")
        settings._byok["model"] = os.environ.get("OPENAI_MODEL", "")
        settings.set_backend("openai")

        # DeepSeek rejects json_schema; replace structured-output with
        # json_object + explicit "json" instruction + Pydantic validation.
        import app.llm as llm_mod
        from langchain_core.messages import HumanMessage
        from langchain_openai import ChatOpenAI

        class _DeepSeekStructured:
            def __init__(self, chat: ChatOpenAI, schema):
                self._chat = chat
                self._schema = schema

            def invoke(self, messages):
                schema_text = json.dumps(
                    self._schema.model_json_schema(), ensure_ascii=False
                )
                hint = (
                    "Respond with ONLY a JSON object that matches this JSON schema:\n"
                    f"{schema_text}"
                )
                patched = list(messages) + [HumanMessage(content=hint)]
                bound = self._chat.bind(
                    response_format={"type": "json_object"}
                )
                response = bound.invoke(patched)
                content = response.content if hasattr(response, "content") else str(response)
                if isinstance(content, list):
                    content = "".join(
                        part.get("text", "") if isinstance(part, dict) else str(part)
                        for part in content
                    )
                return self._schema.model_validate_json(content)

        class _DeepSeekChat:
            def __init__(self, chat: ChatOpenAI):
                self._chat = chat

            def with_structured_output(self, schema, *args, **kwargs):
                del args, kwargs
                return _DeepSeekStructured(self._chat, schema)

            def invoke(self, messages):
                return self._chat.invoke(messages)

            def __getattr__(self, name):
                return getattr(self._chat, name)

        def _get_llm(
            tier,
            *,
            temperature=0,
            max_tokens=2000,
            timeout=None,
            structured_retries=None,
        ):
            del tier, structured_retries
            kwargs = dict(
                model=os.environ.get("OPENAI_MODEL", "deepseek-v4-pro"),
                temperature=temperature,
                max_tokens=max_tokens,
                max_retries=4,
                api_key=os.environ.get("OPENAI_API_KEY"),
                base_url=os.environ.get(
                    "OPENAI_BASE_URL", "https://api.openai.com/v1"
                ),
            )
            if timeout is not None:
                kwargs["timeout"] = timeout
            return _DeepSeekChat(ChatOpenAI(**kwargs))

        llm_mod.get_llm = _get_llm
        # Agents may already have imported the name; rebind common modules.
        for mod_name in (
            "app.agents.parse",
            "app.agents.match",
            "app.agents.resume",
            "app.agents.cover_letter",
            "app.agents.interview",
            "app.agents.critic",
            "app.agents.company",
        ):
            mod = sys.modules.get(mod_name)
            if mod is not None and hasattr(mod, "get_llm"):
                mod.get_llm = _get_llm

        from app.graph import build_graph

        self._app = build_graph(checkpointer=MemorySaver())
        return self._app

    def invoke(self, value, config=None):
        if self._closed:
            raise RuntimeError("Jobsmith binding is closed.")

        jd_text, profile_fields = _parse_case_input(value)
        app = self._ensure_app()

        from app.models import Profile

        profile = Profile(**profile_fields)
        initial = {
            "jd_text": jd_text,
            "profile": profile,
            "artifact_targets": ["cover_letter"],
            "company_research_requested": False,
            "quality_review": False,
            "parsed_job": None,
            "match_report": None,
            "supervisor_decision": None,
            "company_brief": None,
            "tailored_resume": None,
            "cover_letter": None,
            "interview_kit": None,
            "critique": None,
            "revision_count": 0,
            "approved": None,
            "batch": True,
            "errors": [],
            "telemetry": [],
        }
        run_config = dict(config or {})
        run_config.setdefault("configurable", {})
        run_config["configurable"].setdefault("thread_id", "abb-jobsmith-case")
        run_config.setdefault("recursion_limit", 50)
        final_state = app.invoke(initial, config=run_config)

        cover = final_state.get("cover_letter")
        cover_body = getattr(cover, "body", None) or ""
        match = final_state.get("match_report")
        decision = final_state.get("supervisor_decision")
        parsed = final_state.get("parsed_job")
        if not cover_body.strip():
            reason = getattr(decision, "rationale", None) or "no cover letter produced"
            score = getattr(match, "score", None)
            cover_body = (
                f"No cover letter drafted ({reason}"
                + (f"; match_score={score}" if score is not None else "")
                + ")."
            )

        return {
            "cover_letter": cover_body,
            "match_score": getattr(match, "score", None),
            "recommend_proceed": getattr(match, "recommend_proceed", None),
            "job_title": getattr(parsed, "title", ""),
            "company": getattr(parsed, "company", ""),
            "errors": final_state.get("errors") or [],
        }

    def close(self):
        self._closed = True
        self._app = None


def create_graph():
    """Return a fresh binding.

    Example input::

        {"jd_text": "...", "name": "Alex", "skills": ["Python"], "summary": "..."}
    """

    return JobsmithBinding()
