from app.agents import match as match_mod
from app.models import MatchReport
from tests.conftest import FakeLLM


def test_match_profile_returns_report(monkeypatch, demo_profile, sample_parsed_job):
    canned = MatchReport(
        score=82,
        matched=["Python", "LangChain"],
        gaps=["年資略低"],
        suggestions=["補強 multi-agent 專案經驗"],
        recommend_proceed=True,
        reason="技能高度吻合",
    )
    monkeypatch.setattr(match_mod, "get_llm", lambda tier: FakeLLM(canned))

    report = match_mod.match_profile(sample_parsed_job, demo_profile)

    assert isinstance(report, MatchReport)
    assert report.score == 82
    assert report.recommend_proceed is True


def test_match_profile_uses_standard_tier(monkeypatch, demo_profile, sample_parsed_job):
    seen = {}
    canned = MatchReport(score=50, recommend_proceed=False, reason="普通")

    def fake_get_llm(tier):
        seen["tier"] = tier
        return FakeLLM(canned)

    monkeypatch.setattr(match_mod, "get_llm", fake_get_llm)
    match_mod.match_profile(sample_parsed_job, demo_profile)
    assert seen["tier"] == "standard"
