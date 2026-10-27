from app.agents import interview_sim as iv
from app.llm_errors import LLMResponseFormatError
from app.models import (
    AnswerFeedback,
    InterviewQuestion,
    InterviewQuestionList,
    InterviewSummary,
    Profile,
)
from tests.conftest import FakeLLM


class BrokenLLM:
    def with_structured_output(self, schema):
        return self

    def invoke(self, messages):
        raise LLMResponseFormatError("bad json", kind="json")


def _p():
    return Profile(name="王", summary="後端工程師", skills=["Python", "FastAPI"], raw_text="…")


def test_generate_questions(monkeypatch):
    canned = InterviewQuestionList(items=[
        InterviewQuestion(category="技術", question="介紹一個你做過的系統"),
    ])
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(canned))
    qs = iv.generate_questions("AI 工程師 JD", _p(), n=1)
    assert len(qs) == 1 and qs[0].question == "介紹一個你做過的系統"


def test_generate_questions_caps_at_n(monkeypatch):
    canned = InterviewQuestionList(items=[InterviewQuestion(question=f"q{i}") for i in range(10)])
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(canned))
    assert len(iv.generate_questions("JD", _p(), n=6)) == 6


def test_evaluate_answer(monkeypatch):
    fb = AnswerFeedback(score=80, strengths=["具體"], improvements=["量化"], sample_answer="…")
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(fb))
    out = iv.evaluate_answer("題", "答", "JD", _p())
    assert out.score == 80 and out.improvements == ["量化"]


def test_summarize(monkeypatch):
    s = InterviewSummary(overall_score=78, summary="整體不錯", advice=["多準備系統設計"])
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(s))
    out = iv.summarize("JD", [{"question": "q", "answer": "a"}])
    assert out.overall_score == 78 and out.advice


def test_generate_questions_falls_back_when_llm_format_fails(monkeypatch):
    monkeypatch.setattr(iv, "get_llm", lambda tier: BrokenLLM())

    qs = iv.generate_questions("AI 工程師 JD，需要 Python 與 RAG", _p(), n=4)

    assert len(qs) == 4
    assert qs[0].category == "技術"
    assert any("Python" in q.question or "FastAPI" in q.question for q in qs)


def test_evaluate_answer_falls_back_when_llm_format_fails(monkeypatch):
    monkeypatch.setattr(iv, "get_llm", lambda tier: BrokenLLM())

    out = iv.evaluate_answer("請介紹專案", "我用 Python 建置 API，讓延遲降低 30%。", "JD", _p())

    assert 0 <= out.score <= 100
    assert out.strengths
    assert out.improvements
    assert out.sample_answer


def test_summarize_falls_back_when_llm_format_fails(monkeypatch):
    monkeypatch.setattr(iv, "get_llm", lambda tier: BrokenLLM())

    out = iv.summarize("JD", [{"question": "q", "answer": "我用 Python 建置 API。"}])

    assert 0 <= out.overall_score <= 100
    assert out.summary
    assert out.advice


def test_evaluate_answer_falls_back_when_llm_returns_unusable_zero(monkeypatch):
    fb = AnswerFeedback(score=0, strengths=[], improvements=[], sample_answer="")
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(fb))

    out = iv.evaluate_answer(
        "請說明你如何導入 AI agent。",
        "我導入 Codex 與 Claude Code，把規格、測試與實作流程串起來，交付時間下降 30%。",
        "AI Engineer",
        _p(),
    )

    assert out.score > 0
    assert out.strengths
    assert out.improvements


def test_evaluate_answer_falls_back_when_llm_scores_substantive_answer_zero(monkeypatch):
    fb = AnswerFeedback(
        score=0,
        strengths=["有提到工具"],
        improvements=["可以更完整"],
        sample_answer="範例回答",
    )
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(fb))

    out = iv.evaluate_answer(
        "請說明你如何導入 AI agent。",
        "我導入 Codex 與 Claude Code，把規格、測試與實作流程串起來，交付時間下降 30%。",
        "AI Engineer",
        _p(),
    )

    assert out.score > 0
    assert out.score != fb.score


def test_summarize_falls_back_when_llm_returns_unusable_zero(monkeypatch):
    summary = InterviewSummary(overall_score=0, summary="", advice=[])
    monkeypatch.setattr(iv, "get_llm", lambda tier: FakeLLM(summary))

    out = iv.summarize(
        "AI Engineer",
        [{"question": "Q", "answer": "我用 AI agent workflow 改善交付速度 30%。"}],
    )

    assert out.overall_score > 0
    assert out.summary
    assert out.advice
