from app.agents import parse as parse_mod
from app.models import ParsedJob
from tests.conftest import FakeLLM


def test_parse_job_returns_parsed_job(monkeypatch):
    canned = ParsedJob(
        title="AI 工程師",
        company="未來智能股份有限公司",
        required_skills=["Python", "LangChain"],
        language="zh",
    )
    monkeypatch.setattr(parse_mod, "get_llm", lambda tier: FakeLLM(canned))

    result = parse_mod.parse_job("（任意 JD 文字）")

    assert isinstance(result, ParsedJob)
    assert result.company == "未來智能股份有限公司"
    assert "Python" in result.required_skills


def test_parse_job_uses_cheap_tier(monkeypatch):
    seen = {}
    canned = ParsedJob(title="x", company="y")

    def fake_get_llm(tier):
        seen["tier"] = tier
        return FakeLLM(canned)

    monkeypatch.setattr(parse_mod, "get_llm", fake_get_llm)
    parse_mod.parse_job("jd")
    assert seen["tier"] == "cheap"


from pathlib import Path

import pytest


@pytest.mark.live
def test_parse_job_live():
    jd = Path("data/demo_jobs/ai_engineer.txt").read_text(encoding="utf-8")
    result = parse_mod.parse_job(jd)
    assert result.title
    assert result.company == "未來智能股份有限公司"
