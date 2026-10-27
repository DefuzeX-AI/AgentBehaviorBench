from app.agents import refine as mod
from app.models import Profile


class FakeLLM:
    def __init__(self, result):
        self._result = result

    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        return self._result


def _profile():
    return Profile(
        name="王予",
        summary="AI 後端工程師",
        skills=["Python", "FastAPI", "LLM"],
        experiences=["建置多代理求職工具"],
    )


def test_refine_resume_falls_back_when_edit_request_has_no_update(monkeypatch):
    monkeypatch.setattr(
        mod,
        "get_llm",
        lambda tier, **kw: FakeLLM(mod.RefineResult(reply="請貼上履歷與 JD")),
    )

    out = mod.refine_document(
        "resume",
        "舊摘要\n- 舊條列",
        [{"role": "user", "content": "請更強調 LLM 和後端 API"}],
        "AI Engineer JD",
        _profile(),
    )

    assert out.updated_summary
    assert out.updated_bullets
    assert "LLM" in out.updated_summary or any("LLM" in b for b in out.updated_bullets)


def test_refine_cover_falls_back_when_edit_request_has_no_update(monkeypatch):
    monkeypatch.setattr(
        mod,
        "get_llm",
        lambda tier, **kw: FakeLLM(mod.RefineResult(reply="請貼上求職信")),
    )

    out = mod.refine_document(
        "cover",
        "舊求職信",
        [{"role": "user", "content": "請修改得更專業"}],
        "AI Engineer JD",
        _profile(),
    )

    assert out.updated_subject
    assert out.updated_body
