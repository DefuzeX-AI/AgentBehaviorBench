from app.agents import interview as iv_mod
from app.models import CompanyBrief, InterviewKit
from tests.conftest import FakeLLM


def test_prepare_interview_returns_kit(monkeypatch, demo_profile, sample_parsed_job):
    canned = InterviewKit(
        technical_questions=["解釋 RAG 流程"],
        reverse_questions=["團隊目前的 agent 架構是？"],
        cautions=["注意加班文化"],
    )
    monkeypatch.setattr(iv_mod, "get_llm", lambda tier: FakeLLM(canned))
    company = CompanyBrief(company="未來智能", red_flags=["加班多"])

    kit = iv_mod.prepare_interview(sample_parsed_job, demo_profile, company)

    assert isinstance(kit, InterviewKit)
    assert kit.reverse_questions


def test_prepare_interview_handles_none_company(monkeypatch, demo_profile, sample_parsed_job):
    canned = InterviewKit(technical_questions=["Q1"])
    monkeypatch.setattr(iv_mod, "get_llm", lambda tier: FakeLLM(canned))

    kit = iv_mod.prepare_interview(sample_parsed_job, demo_profile, None)

    assert isinstance(kit, InterviewKit)


def test_prepare_interview_uses_standard_tier(monkeypatch, demo_profile, sample_parsed_job):
    seen = {}
    canned = InterviewKit()

    def fake_get_llm(tier):
        seen["tier"] = tier
        return FakeLLM(canned)

    monkeypatch.setattr(iv_mod, "get_llm", fake_get_llm)
    iv_mod.prepare_interview(sample_parsed_job, demo_profile, None)
    assert seen["tier"] == "standard"


def test_prepare_interview_includes_feedback(monkeypatch, demo_profile, sample_parsed_job):
    captured = {}
    canned = InterviewKit(technical_questions=["Q"])

    class _CapLLM:
        def with_structured_output(self, schema):
            return self
        def invoke(self, messages):
            captured["human"] = messages[-1][1]
            return canned

    monkeypatch.setattr(iv_mod, "get_llm", lambda tier: _CapLLM())
    iv_mod.prepare_interview(sample_parsed_job, demo_profile, None, ["多準備系統設計題"])
    assert "多準備系統設計題" in captured["human"]
