from app.models import Profile, ResumeAssessment, ResumeIssue
from app.store import resume_checks


def _assessment(mode: str = "deep", reason: str = "") -> ResumeAssessment:
    return ResumeAssessment(
        overall_score=82,
        clarity_score=80,
        impact_score=78,
        ats_keyword_score=84,
        localization_score=85,
        completeness_score=83,
        summary="履歷結構清楚，量化成果可再補強。",
        strengths=["定位清楚"],
        issues=[ResumeIssue(severity="medium", area="量化成果", problem="數字不足", fix="補上影響範圍")],
        assessment_mode=mode,
        fallback_reason=reason,
    )


def test_resume_assessment_tracks_deep_or_fallback_mode():
    deep = _assessment()
    fallback = _assessment("fallback", "Codex CLI returned invalid JSON")

    assert deep.assessment_mode == "deep"
    assert deep.fallback_reason == ""
    assert fallback.assessment_mode == "fallback"
    assert "invalid JSON" in fallback.fallback_reason


def test_save_list_get_delete_resume_check():
    profile = Profile(name="Alex Chen", summary="Backend engineer", skills=["FastAPI"]).model_dump()
    assessment = _assessment("fallback", "bad PDF structure").model_dump()

    cid = resume_checks.save_check(
        label="Alex Chen 履歷健檢",
        resume_label="resume.pdf",
        profile=profile,
        assessment=assessment,
    )
    rows = resume_checks.list_checks()
    row = next(r for r in rows if r["id"] == cid)

    assert row["label"] == "Alex Chen 履歷健檢"
    assert row["resume_label"] == "resume.pdf"
    assert row["overall_score"] == 82
    assert row["assessment_mode"] == "fallback"
    full = resume_checks.get_check(cid)
    assert full["profile"]["name"] == "Alex Chen"
    assert full["assessment"]["issues"][0]["area"] == "量化成果"
    assert full["fallback_reason"] == "bad PDF structure"

    resume_checks.delete_check(cid)
    assert resume_checks.get_check(cid) is None
