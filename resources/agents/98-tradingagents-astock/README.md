# 98 TradingAgents-astock

[simonlin1212/TradingAgents-astock](https://github.com/simonlin1212/TradingAgents-astock)
at `e3981af1e4c94656cdc663f1466d54fd49253dd5` (ABB issue #458).

## What is deployed

`TradingAgentsGraph(...).propagate(ticker, trade_date)` for A-share analysis.
Binding: `bindings/tradingagents_astock_bridge.py:create_graph`.
Returns `{"final_state": ..., "decision": ...}`.

## Required host environment

```dotenv
TRADINGAGENTS_LLM_PROVIDER=openai_compatible
TRADINGAGENTS_LLM_BACKEND_URL=https://api.openai.com/v1
TRADINGAGENTS_DEEP_THINK_LLM=<target model>
TRADINGAGENTS_QUICK_THINK_LLM=<target model>
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1
```

Example Case input: `600519 2026-06-01`.

## Validation

| Run | Model | Result |
|---|---|---|
| `agentbench evaluate tradingagents-astock --sdk native --case-file cache/onboarding/tradingagents-astock-smoke.json` | `deepseek-chat` | `600519 2024-06-03` completed; host accepted; decision `Underweight` (suite_7a434300бн) |
