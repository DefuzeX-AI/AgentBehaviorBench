"""辩论历史滚动窗口压缩。

多空 / 风险辩手每轮把完整 `history` 注入 prompt，同时再单独注入一次
`current_response`（恰是 history 的最后一条发言），导致最新发言被重复注入、
注入 token 随辩论轮数平方增长。这里提供 `compact_history`：保留最近
`max_turns` 条发言全文，更早的压成「角色: 首句要点」一行，供辩手在注入前调用。
"""

from __future__ import annotations

import re

# 辩手把每条发言拼成「{角色} Analyst: {正文}」（见 bull/bear 及三个 risk debator 的
# argument 构造）。按「换行 + 角色前缀」切分出各条发言；正文几乎不会出现这类前缀。
_ROUND_SPLIT = re.compile(
    r"\n(?=(?:Bull|Bear|Aggressive|Conservative|Neutral) Analyst:)"
)

# 早期发言压成一行时，首句截断到该长度，避免摘要本身再膨胀。
_SUMMARY_MAX_CHARS = 120


def compact_history(history: str, max_turns: int = 4) -> str:
    """把辩论历史压到「最近 max_turns 条全文 + 更早每条一句摘要」。

    `history` 是纯字符串累积字段（InvestDebateState.history /
    RiskDebateState.history）。发言数不超过 max_turns 时原样返回；超过时把更早的
    发言压成「角色: 首句」一行。默认配置下（多空各 1 轮 = 2 条、风险各 1 轮 =
    3 条）不会触发，仅当调大 max_debate_rounds / max_risk_discuss_rounds 时生效。
    """
    if not history.strip():
        return ""

    turns = [t for t in _ROUND_SPLIT.split(history) if t.strip()]
    if len(turns) <= max_turns:
        return history

    head = turns[:-max_turns]
    tail = turns[-max_turns:]
    summaries = [f"{_speaker(t)}: {_first_sentence(t)}" for t in head]

    return (
        "[早期论点摘要]\n"
        + "\n".join(summaries)
        + "\n\n[近期完整辩论]\n"
        + "\n".join(tail)
    )


def _speaker(turn: str) -> str:
    """取一条发言开头的角色名（如 'Bull Analyst'），识别不到回退 'Analyst'。"""
    text = turn.strip()
    for name in ("Bull", "Bear", "Aggressive", "Conservative", "Neutral"):
        if text.startswith(f"{name} Analyst"):
            return f"{name} Analyst"
    return "Analyst"


def _first_sentence(turn: str) -> str:
    """取一条发言正文的第一句，截断到 _SUMMARY_MAX_CHARS。"""
    body = turn.strip()
    # 去掉开头的「角色: 」前缀（partition 只取第一个冒号后的正文）
    _, _, body = body.partition(":")
    body = body.strip()
    # 取第一句（按中英文句号 / 换行切，取最早出现者），无句号则整段
    stops = [i for i in (body.find(ch) for ch in (".", "。", "!", "！", "?", "？", "\n")) if i != -1]
    if stops:
        body = body[: min(stops) + 1]
    body = body.strip()
    if len(body) > _SUMMARY_MAX_CHARS:
        return body[:_SUMMARY_MAX_CHARS] + "…"
    return body
