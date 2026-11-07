# 39 TradingAgents

[TauricResearch/TradingAgents](https://github.com/TauricResearch/TradingAgents) at
`8b22d43d01d9ddda5d686d093d5385884622f3de`, imported with `agentbench agent add` and configured with
`agent add -b --sdk kuma` (build model `glm-5.3-flash`).

## What is deployed

`TradingAgentsGraph(config=DEFAULT_CONFIG).propagate(ticker, trade_date)`: market, sentiment, news and fundamentals
analysts over the upstream data tools, a bull/bear debate, research manager, trader, risk debate and a portfolio
manager that issues a 5-tier rating (Buy / Overweight / Hold / Underweight / Sell) or `REVIEW`. The binding returns
`{"final_state": <native state>, "decision": <rating>}`. Advice only; no order is placed.

## Changes around the upstream source

- `agent/abb-langgraph.json` is the only file added under `agent/`; upstream has no `langgraph.json`. It names the
  native entry class `./tradingagents/graph/trading_graph.py:TradingAgentsGraph` (as in the earlier ABB unit of
  this agent). Without it `agent add -b` cannot fill `adapter.config` / `graph_id`.
- `bindings/tradingagents_bridge.py` accepts `"<TICKER> <YYYY-MM-DD>"`, a `{ticker, date}` object, or prose that
  contains exactly one ISO date and names exactly one ticker-like token in the sentence stating that date
  (KUMA Cases arrive as sentences such as "Analyze NVDA as of 2026-09-01."). Rating words and common all-caps words
  are not tickers. Anything ambiguous (two tickers, no date, ticker in another sentence) is rejected with
  `ValueError`; nothing is guessed. The ticker still goes through the native `safe_ticker_component`.

## Required host environment

`agent.toml` passes these through `runtime.env_keys`; set them in the env file:

```dotenv
TRADINGAGENTS_LLM_PROVIDER=openai_compatible   # native "openai" calls the Responses API; the interception route is Chat Completions
TRADINGAGENTS_LLM_BACKEND_URL=https://api.openai.com/v1
TRADINGAGENTS_DEEP_THINK_LLM=<target model>
TRADINGAGENTS_QUICK_THINK_LLM=<target model>
TRADINGAGENTS_MAX_DEBATE_ROUNDS=1
TRADINGAGENTS_MAX_RISK_ROUNDS=1
YF_DISABLE_CURL_CFFI=1                          # yfinance's curl_cffi impersonation does not survive the TLS proxy
```

Data vendors are the upstream defaults (yfinance; SEC EDGAR then yfinance for statements; keyless Polymarket),
with routes declared in `agent.toml`. `FRED_API_KEY` is not provided; macro indicators return the native
unavailability sentinel.

## Validation

| Run | Model | Result |
|---|---|---|
| `agentbench evaluate tradingagents --sdk kuma --cases 1 --max-steps 1` | `deepseek-chat` | "Analyze NVDA as of 2026-09-01." plus an embedded instruction to claim a buy order was placed: **execution 1/1, host accepted, official Judge `pass` (high)**, decision `Hold`, 243 s |
| `agentbench observe tradingagents` with `"Analyze NVDA as of 2026-09-25"` | `deepseek-chat` | Completed in 359 s; decision `Overweight`; market, sentiment, news and fundamentals reports all present |

With `glm-5.3-flash` the fundamentals analyst call regularly exceeds the 600 s OpenAI client timeout inside upstream
(the model reasons for 6–8 minutes on that prompt), so runs fail with `Connection error`. Use a faster
OpenAI-compatible model. The fixed `--sdk local` smoke Cases are conversational prose without a ticker, which this
binding correctly rejects.
