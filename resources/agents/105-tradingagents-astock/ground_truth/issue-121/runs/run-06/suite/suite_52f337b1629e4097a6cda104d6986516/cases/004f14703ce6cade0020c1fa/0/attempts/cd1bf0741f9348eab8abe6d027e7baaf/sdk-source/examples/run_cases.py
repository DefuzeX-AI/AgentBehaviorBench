"""Batch runner: analyse multiple A-stock tickers and save results to examples/cases/.

每只标的会生成与 CLI 一致的完整报告 `complete_report.md`（含分析师 / 研究 / 交易 /
风险 / 组合五个分区），并额外落一份 summary.json 便于程序化读取。

Usage:
    uv run python examples/run_cases.py          # run all cases
    uv run python examples/run_cases.py 688017   # run a single ticker

(采纳自社区贡献 #68 @zcc2xj，复用 cli.main.save_report_to_disk 生成 complete_report.md)
"""

from __future__ import annotations

import json
import sys
import time
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from cli.main import save_report_to_disk

# ── Config ───────────────────────────────────────────────────────────────────

CASES_DIR = Path(__file__).parent / "cases"
CASES_DIR.mkdir(parents=True, exist_ok=True)

TRADE_DATE = "2026-05-12"

# 10 tickers across different sectors
# fmt: off
TICKERS = {
    "688017": "绿的谐波 (科创板·谐波减速器)",
    "300750": "宁德时代 (创业板·动力电池)",
    "600519": "贵州茅台 (主板·白酒龙头)",
    "000858": "五粮液 (主板·白酒)",
    "300059": "东方财富 (创业板·互联网券商)",
    "601012": "隆基绿能 (主板·光伏)",
    "300760": "迈瑞医疗 (创业板·医疗器械)",
    "688981": "中芯国际 (科创板·芯片代工)",
    "002594": "比亚迪 (主板·新能源汽车)",
    "300124": "汇川技术 (创业板·工业自动化)",
}
# fmt: on


def build_config() -> dict:
    """Build the TradingAgents config for case runs.

    默认用 MiniMax；换成你自己的 provider/model 时改 llm_provider 与两个 *_llm 即可。
    """
    config = DEFAULT_CONFIG.copy()
    config["llm_provider"] = "minimax"
    config["deep_think_llm"] = "MiniMax-M2.7"
    config["quick_think_llm"] = "MiniMax-M2.7-highspeed"
    config["data_vendors"] = {
        "core_stock_apis": "a_stock",
        "technical_indicators": "a_stock",
        "fundamental_data": "a_stock",
        "news_data": "a_stock",
        "signal_data": "a_stock",
    }
    config["max_debate_rounds"] = 1
    config["max_risk_discuss_rounds"] = 1
    config["output_language"] = "Chinese"
    return config


def run_single(ticker: str, label: str, config: dict) -> None:
    """Run one ticker and save the complete analysis report."""
    print(f"\n{'=' * 60}")
    print(f"Analysing {ticker} — {label}")
    print(f"Trade date: {TRADE_DATE}")
    print(f"{'=' * 60}\n")

    start_time = time.time()
    ta = TradingAgentsGraph(debug=True, config=config)

    final_state = None
    decision = ""
    try:
        final_state, decision = ta.propagate(ticker, TRADE_DATE)
    except Exception as e:
        decision = f"ERROR: {e}"

    elapsed = time.time() - start_time

    if final_state is None:
        print(f"\n❌ Failed: {decision}")
        return

    stock_name = label.split("(")[0].strip()
    ts = datetime.now().strftime("%Y%m%d_%H%M")
    dir_name = f"{ticker}_{stock_name}_{ts}"
    ticker_dir = CASES_DIR / dir_name

    report_path = save_report_to_disk(final_state, ticker, ticker_dir)
    renamed_report = ticker_dir / f"{dir_name}.md"
    report_path.rename(renamed_report)
    print(f"\n✅ Report saved to {renamed_report} ({elapsed:.0f}s)")

    summary_path = ticker_dir / "summary.json"
    _save_json_summary(summary_path, ticker, label, elapsed, final_state, decision)


def _save_json_summary(
    summary_path: Path,
    ticker: str,
    label: str,
    elapsed: float,
    final_state: dict,
    decision: str,
) -> None:
    """Save a JSON summary with all report sections for programmatic use."""
    summary = {
        "ticker": ticker,
        "label": label,
        "trade_date": TRADE_DATE,
        "run_time": datetime.now().isoformat(),
        "duration_seconds": round(elapsed),
        "signal": decision,
        "reports": {},
    }

    report_keys = [
        "market_report",
        "sentiment_report",
        "news_report",
        "fundamentals_report",
        "policy_report",
        "hot_money_report",
        "lockup_report",
        "investment_plan",
        "trader_investment_plan",
        "final_trade_decision",
    ]
    for key in report_keys:
        val = final_state.get(key, "")
        if val:
            summary["reports"][key] = val[:3000]

    debate = final_state.get("investment_debate_state", {})
    if debate:
        summary["reports"]["bull_history"] = debate.get("bull_history", "")[:2000]
        summary["reports"]["bear_history"] = debate.get("bear_history", "")[:2000]
        summary["reports"]["research_manager"] = debate.get("judge_decision", "")[:2000]

    risk = final_state.get("risk_debate_state", {})
    if risk:
        summary["reports"]["aggressive_analyst"] = risk.get("aggressive_history", "")[:2000]
        summary["reports"]["conservative_analyst"] = risk.get("conservative_history", "")[:2000]
        summary["reports"]["neutral_analyst"] = risk.get("neutral_history", "")[:2000]
        summary["reports"]["portfolio_manager"] = risk.get("judge_decision", "")[:2000]

    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)


def main() -> None:
    config = build_config()

    # Allow single ticker override from CLI
    if len(sys.argv) > 1:
        ticker = sys.argv[1]
        label = TICKERS.get(ticker, ticker)
        run_single(ticker, label, config)
        return

    # Run all
    print(f"Running {len(TICKERS)} cases...")
    for ticker, label in TICKERS.items():
        run_single(ticker, label, config)
        print(f"\n{'─' * 40}")

    print(f"\n{'=' * 60}")
    print(f"All {len(TICKERS)} cases complete. Results in {CASES_DIR}/")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
