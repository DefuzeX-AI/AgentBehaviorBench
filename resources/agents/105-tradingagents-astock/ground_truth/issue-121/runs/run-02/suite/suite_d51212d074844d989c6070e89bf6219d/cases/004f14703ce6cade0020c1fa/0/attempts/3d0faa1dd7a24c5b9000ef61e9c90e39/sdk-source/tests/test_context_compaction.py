"""辩论历史滚动窗口压缩 + 辩手去冗余的单元测试。

覆盖 compact_history 纯函数的正常 / 边界 / 兼容路径，以及辩手节点去掉
current_response 注入后「对方最后一条发言只出现一次」的确定性收益。
"""

from __future__ import annotations

import pytest

from tradingagents.agents.utils.context import (
    _SUMMARY_MAX_CHARS,
    _first_sentence,
    _speaker,
    compact_history,
)


def _make_history(*turns: str) -> str:
    """按辩手的累积方式拼接 history（首条前也有一个换行）。"""
    return "\n" + "\n".join(turns)


@pytest.mark.unit
class TestCompactHistory:
    def test_empty_history_returns_empty(self):
        assert compact_history("") == ""
        assert compact_history("   \n  ") == ""

    def test_under_max_turns_returns_unchanged(self):
        history = _make_history("Bull Analyst: 看多论点。", "Bear Analyst: 看空论点。")
        assert compact_history(history) == history

    def test_exact_max_turns_returns_unchanged(self):
        history = _make_history(
            "Bull Analyst: a。", "Bear Analyst: b。", "Bull Analyst: c。", "Bear Analyst: d。"
        )
        assert compact_history(history, max_turns=4) == history

    def test_over_max_turns_compacts_old_rounds(self):
        history = _make_history(
            "Bull Analyst: 早期看多论点一。早期看多论点二。",
            "Bear Analyst: 早期看空论点一。早期看空论点二。",
            "Bull Analyst: 近期论点A。",
            "Bear Analyst: 近期论点B。",
            "Bull Analyst: 近期论点C。",
            "Bear Analyst: 近期论点D。",
        )
        out = compact_history(history, max_turns=4)

        assert "[早期论点摘要]" in out
        assert "[近期完整辩论]" in out
        # 早期发言被压成首句摘要，第二句消失
        assert "早期看多论点二" not in out
        assert "早期看空论点二" not in out
        # 首句仍作为摘要保留
        assert "早期看多论点一" in out
        # 近期发言保留全文
        assert "近期论点D。" in out


@pytest.mark.unit
class TestHelpers:
    def test_speaker_extraction(self):
        assert _speaker("Bull Analyst: x") == "Bull Analyst"
        assert _speaker("Aggressive Analyst: x") == "Aggressive Analyst"
        assert _speaker("Conservative Analyst: x") == "Conservative Analyst"
        assert _speaker("Neutral Analyst: x") == "Neutral Analyst"

    def test_speaker_fallback(self):
        assert _speaker("没有前缀") == "Analyst"

    def test_first_sentence_truncates_long_text(self):
        result = _first_sentence("Bull Analyst: " + "x" * 300)
        assert result.endswith("…")
        assert len(result) == _SUMMARY_MAX_CHARS + 1


class _FakeResponse:
    def __init__(self, content: str):
        self.content = content


@pytest.mark.unit
class TestDebatorDedup:
    def test_bull_prompt_dedupes_last_bear_argument(self):
        from tradingagents.agents.researchers.bull_researcher import create_bull_researcher

        captured = {}

        class FakeLLM:
            def invoke(self, prompt):
                captured["prompt"] = prompt
                return _FakeResponse("看多论点。")

        bear_arg = "Bear Analyst: 看空论点一。"
        state = {
            "market_report": "m",
            "sentiment_report": "s",
            "news_report": "n",
            "fundamentals_report": "f",
            "policy_report": "p",
            "hot_money_report": "h",
            "lockup_report": "l",
            "data_quality_summary": "q",
            "investment_debate_state": {
                "history": "\n" + bear_arg,
                "bull_history": "",
                "bear_history": bear_arg,
                "current_response": bear_arg,
                "count": 1,
            },
        }
        create_bull_researcher(FakeLLM())(state)
        assert captured["prompt"].count(bear_arg) == 1

    def test_aggressive_prompt_dedupes_last_arguments(self):
        from tradingagents.agents.risk_mgmt.aggressive_debator import (
            create_aggressive_debator,
        )

        captured = {}

        class FakeLLM:
            def invoke(self, prompt):
                captured["prompt"] = prompt
                return _FakeResponse("激进论点。")

        cons_arg = "Conservative Analyst: 保守论点。"
        neu_arg = "Neutral Analyst: 中性论点。"
        state = {
            "market_report": "m",
            "sentiment_report": "s",
            "news_report": "n",
            "fundamentals_report": "f",
            "policy_report": "p",
            "hot_money_report": "h",
            "lockup_report": "l",
            "trader_investment_plan": "t",
            "risk_debate_state": {
                "history": "\n" + cons_arg + "\n" + neu_arg,
                "aggressive_history": "",
                "conservative_history": cons_arg,
                "neutral_history": neu_arg,
                "latest_speaker": "Neutral",
                "current_aggressive_response": "",
                "current_conservative_response": cons_arg,
                "current_neutral_response": neu_arg,
                "count": 2,
            },
        }
        create_aggressive_debator(FakeLLM())(state)
        prompt = captured["prompt"]
        assert prompt.count(cons_arg) == 1
        assert prompt.count(neu_arg) == 1
