"""End-to-end test: run TradingAgents pipeline on A-stock 688017 via Kimi 2.6."""

from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG

from dotenv import load_dotenv

load_dotenv()

config = DEFAULT_CONFIG.copy()

# --- LLM: Kimi 2.6 via Anthropic-compatible API ---
config["llm_provider"] = "anthropic"
config["deep_think_llm"] = "claude-sonnet-4-6"   # Kimi maps internally
config["quick_think_llm"] = "claude-sonnet-4-6"
config["backend_url"] = "https://api.kimi.com/coding/"

# --- Data: A-stock vendor (mootdx + tencent + eastmoney + sina) ---
config["data_vendors"] = {
    "core_stock_apis": "a_stock",
    "technical_indicators": "a_stock",
    "fundamental_data": "a_stock",
    "news_data": "a_stock",
}

# --- Debate settings: minimal for first test ---
config["max_debate_rounds"] = 1
config["max_risk_discuss_rounds"] = 1
config["output_language"] = "Chinese"

print("=" * 60)
print("TradingAgents-Astock E2E Test")
print("Ticker: 688017")
print("Trade date: 2026-04-30")
print("LLM: Kimi 2.6 via Anthropic API")
print("Data: a_stock (mootdx + tencent + eastmoney + sina)")
print("=" * 60)

ta = TradingAgentsGraph(debug=True, config=config)

_, decision = ta.propagate("688017", "2026-04-30")
print("\n" + "=" * 60)
print("FINAL DECISION:")
print("=" * 60)
print(decision)
