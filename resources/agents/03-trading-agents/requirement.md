# TradingAgents requirements

Call unchanged native TradingAgentsGraph.propagate(ticker, date) for each Input.
Inputs must be complete ticker/date objects (JSON-encoded text for official Kuma
Case generation). Reject freeform chat and extra fields instead of silently
discarding instructions or presenting them as historical decision lessons.

Run the native market analyst, bull/bear debate, trader, risk analysts and
portfolio manager. Preserve the native public full final_state and separate
decision signal. The Agent owns its original decision log, outcome reflection,
report files and any enabled checkpoint behavior. Keep its instance and private
writable storage throughout a Case; do not read/write synthetic history in BBA.
Other Cases supply no memory. Native historical-date eligibility rules remain
unchanged; repeated Inputs do not imply arbitrary conversational recall.

Ground financial claims in real yfinance tools and clearly state unavailable or
conflicting evidence. This deployment has no brokerage integration and must not
execute real orders. Kuma input/output details and configured limits are in
evaluation/profile.md. Current readiness is recorded in resources/registry.toml;
old history-wrapper acceptance does not validate this native task interface.
