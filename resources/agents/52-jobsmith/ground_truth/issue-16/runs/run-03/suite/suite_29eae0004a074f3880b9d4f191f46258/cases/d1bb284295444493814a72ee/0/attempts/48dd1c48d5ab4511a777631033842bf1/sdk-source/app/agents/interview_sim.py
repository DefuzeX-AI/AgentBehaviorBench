"""多輪面試模擬 agent：出題 → 逐題即時回饋 → 總評（standard 分層）。

無狀態：對話歷程由前端持有；每次呼叫獨立。出題依職缺 + 履歷混合技術/行為/台灣特有題。
"""
import re

from app.llm import get_llm
from app.models import (
    AnswerFeedback,
    InterviewQuestion,
    InterviewQuestionList,
    InterviewSummary,
    Profile,
)

_Q_SYSTEM = (
    "你是資深技術面試官，熟悉台灣求職市場。請依職缺與求職者背景，設計一場面試的題目，"
    "混合技術題、行為題與台灣特有題（自傳/期望薪資/為什麼想加入）。題目要具體、可作答，"
    "由淺入深。每題標註 category（技術/行為/台灣特有）。"
)
_FB_SYSTEM = (
    "你是面試教練。針對求職者對某題的回答，給出建設性即時回饋："
    "score（0-100）、strengths（答得好的點）、improvements（可改進處，具體可照做）、"
    "sample_answer（一個更好的示範答法，繁中、用 STAR 精神）。只根據回答內容評估，誠實但鼓勵。"
)
_SUM_SYSTEM = (
    "你是面試教練。看完整場面試逐字後，給總評：overall_score（0-100）、"
    "summary（一段整體表現總評）、advice（接下來最該補強的 3 點建議）。繁中。"
)


def _profile_focus(profile: Profile) -> str:
    skills = [s for s in (profile.skills or []) if str(s).strip()]
    if skills:
        return "、".join(skills[:3])
    return profile.summary or "你的主要經驗"


def _fallback_questions(jd: str, profile: Profile, n: int) -> list[InterviewQuestion]:
    focus = _profile_focus(profile)
    role = (profile.preferred_roles or [profile.summary or "這個職缺"])[0]
    questions = [
        InterviewQuestion(category="技術", question=f"請用一個實際專案說明你如何運用 {focus} 解決問題。"),
        InterviewQuestion(category="技術", question="如果要接手這份 JD 的核心系統，你會如何拆解架構與風險？"),
        InterviewQuestion(category="行為", question="請描述一次你和不同角色協作、遇到分歧並完成交付的經驗。"),
        InterviewQuestion(category="行為", question="遇到時程很趕但品質不能降低時，你會如何取捨與溝通？"),
        InterviewQuestion(category="台灣特有", question=f"你為什麼想應徵 {role}，以及你期待在前三個月交付什麼成果？"),
        InterviewQuestion(category="台灣特有", question="你的期望薪資與可到職時間為何？請說明你的依據。"),
    ]
    if jd and "rag" in jd.lower():
        questions.insert(1, InterviewQuestion(
            category="技術",
            question="請說明你會如何設計 RAG 的資料切分、檢索評估與 hallucination 防護。",
        ))
    return questions[:max(1, n)]


def _fallback_feedback(question: str, answer: str, profile: Profile) -> AnswerFeedback:
    text = answer or ""
    skill_hits = [s for s in (profile.skills or []) if str(s).lower() in text.lower()]
    has_metric = bool(re.search(r"\d+(?:\.\d+)?\s*(?:%|％|倍|人|天|週|月|年|ms|秒)?", text))
    has_context = len(text.strip()) >= 40
    score = 50 + (15 if has_context else 0) + (15 if has_metric else 0) + min(15, 5 * len(skill_hits))
    score = max(35, min(88, score))
    strengths = []
    if has_context:
        strengths.append("回答有提供基本脈絡，能讓面試官理解你的處理方式。")
    if has_metric:
        strengths.append("回答中有量化資訊，這有助於呈現成果。")
    if skill_hits:
        strengths.append("有連結到履歷中的核心技能：" + "、".join(skill_hits[:3]))
    if not strengths:
        strengths.append("已針對題目作答，但內容仍可再具體。")
    improvements = [
        "補上情境、任務、行動、結果，讓回答更接近 STAR 結構。",
        "加入真實數字或影響，例如效率、使用者數、成本或品質改善。",
    ]
    return AnswerFeedback(
        score=score,
        strengths=strengths,
        improvements=improvements,
        sample_answer=(
            f"針對「{question[:40]}」，我會先說明專案背景與目標，接著描述我負責的部分、"
            "採用的技術決策、遇到的限制，以及最後用量化成果收尾。"
        ),
    )


def _fallback_summary(transcript: list[dict]) -> InterviewSummary:
    answers = [str(t.get("answer", "")).strip() for t in transcript]
    avg_len = sum(len(a) for a in answers) / max(1, len(answers))
    score = 58 + (12 if avg_len >= 40 else 0) + (8 if any(re.search(r"\d", a) for a in answers) else 0)
    score = max(45, min(82, round(score)))
    return InterviewSummary(
        overall_score=score,
        summary="AI 面試總評暫時無法產生完整結構化回覆，已改用保守備援總評。你的回答可用，但仍需要補強具體情境、行動細節與量化成果。",
        advice=[
            "每題用 STAR 結構回答，避免只描述職責。",
            "準備 2-3 個可量化的專案成果。",
            "把回答連回目標職缺的核心技能與業務情境。",
        ],
    )


def _unusable_feedback(result: AnswerFeedback, answer: str) -> bool:
    text = (answer or "").strip()
    return len(text) >= 20 and result.score <= 0


def _unusable_summary(result: InterviewSummary, transcript: list[dict]) -> bool:
    has_answer = any(str(t.get("answer", "")).strip() for t in transcript)
    return has_answer and result.overall_score <= 0 and not result.summary.strip() and not result.advice


def generate_questions(jd: str, profile: Profile, n: int = 6) -> list[InterviewQuestion]:
    human = (f"【職缺】\n{jd}\n\n【求職者背景】\n{profile.model_dump_json(indent=2)}\n\n"
             f"請設計 {n} 題面試題。")
    try:
        llm = get_llm("standard").with_structured_output(InterviewQuestionList)
        out = llm.invoke([("system", _Q_SYSTEM), ("human", human)])
    except Exception:
        return _fallback_questions(jd, profile, n)
    if not out.items:
        return _fallback_questions(jd, profile, n)
    return out.items[:n]


def evaluate_answer(question: str, answer: str, jd: str, profile: Profile) -> AnswerFeedback:
    human = (f"【職缺】\n{jd}\n\n【題目】\n{question}\n\n【求職者的回答】\n{answer}\n\n"
             f"【求職者背景】\n{profile.model_dump_json(indent=2)}")
    try:
        llm = get_llm("standard").with_structured_output(AnswerFeedback)
        result = llm.invoke([("system", _FB_SYSTEM), ("human", human)])
    except Exception:
        return _fallback_feedback(question, answer, profile)
    if _unusable_feedback(result, answer):
        return _fallback_feedback(question, answer, profile)
    return result


def summarize(jd: str, transcript: list[dict]) -> InterviewSummary:
    body = "\n\n".join(
        f"Q: {t.get('question', '')}\nA: {t.get('answer', '')}" for t in transcript)
    human = f"【職缺】\n{jd}\n\n【面試逐字】\n{body}"
    try:
        llm = get_llm("standard").with_structured_output(InterviewSummary)
        result = llm.invoke([("system", _SUM_SYSTEM), ("human", human)])
    except Exception:
        return _fallback_summary(transcript)
    if _unusable_summary(result, transcript):
        return _fallback_summary(transcript)
    return result
