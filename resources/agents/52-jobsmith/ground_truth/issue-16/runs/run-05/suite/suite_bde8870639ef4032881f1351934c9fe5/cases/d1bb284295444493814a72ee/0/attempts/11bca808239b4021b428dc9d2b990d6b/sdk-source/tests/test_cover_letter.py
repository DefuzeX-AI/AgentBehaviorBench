from app.agents import cover_letter as cl_mod
from app.models import CompanyBrief, CoverLetter
from tests.conftest import FakeLLM


def test_write_cover_letter_returns_letter(monkeypatch, demo_profile, sample_parsed_job):
    canned = CoverLetter(body="敬啟者，我對貴司的 AI 職缺深感興趣……",
                         company_facts_used=["剛完成 B 輪募資"])
    monkeypatch.setattr(cl_mod, "get_llm", lambda tier: FakeLLM(canned))
    company = CompanyBrief(company="未來智能", funding="B 輪")

    letter = cl_mod.write_cover_letter(sample_parsed_job, demo_profile, company)

    assert isinstance(letter, CoverLetter)
    assert letter.body


def test_write_cover_letter_handles_none_company(monkeypatch, demo_profile, sample_parsed_job):
    canned = CoverLetter(body="敬啟者……")
    monkeypatch.setattr(cl_mod, "get_llm", lambda tier: FakeLLM(canned))

    letter = cl_mod.write_cover_letter(sample_parsed_job, demo_profile, None)

    assert isinstance(letter, CoverLetter)


def test_write_cover_letter_uses_standard_tier(monkeypatch, demo_profile, sample_parsed_job):
    seen = {}
    canned = CoverLetter(body="x")

    def fake_get_llm(tier):
        seen["tier"] = tier
        return FakeLLM(canned)

    monkeypatch.setattr(cl_mod, "get_llm", fake_get_llm)
    cl_mod.write_cover_letter(sample_parsed_job, demo_profile, None)
    assert seen["tier"] == "standard"


def test_write_cover_letter_includes_feedback(monkeypatch, demo_profile, sample_parsed_job):
    captured = {}
    canned = CoverLetter(body="改好的")

    class _CapLLM:
        def with_structured_output(self, schema):
            return self
        def invoke(self, messages):
            captured["human"] = messages[-1][1]
            return canned

    monkeypatch.setattr(cl_mod, "get_llm", lambda tier: _CapLLM())
    cl_mod.write_cover_letter(sample_parsed_job, demo_profile, None, ["語氣更誠懇"])
    assert "語氣更誠懇" in captured["human"]
