# TradingAgents requirements

Run the official market analyst and subsequent native debate/risk workflow.
The deployment explicitly configures AAPL and research date 2026-09-11. Plain
text supplies the research request; user JSON may explicitly override ticker/date.
Follow-ups use this Case's prior user turns and final answers. User corrections
must be carried forward; other Cases supply no memory. Ground financial claims
in real yfinance tools and clearly state unavailable or conflicting evidence.
This deployment has no brokerage integration and must not execute real orders.
Kuma input/output details and configured limits are in evaluation/profile.md.
Status: adapting; real service certification remains pending.
