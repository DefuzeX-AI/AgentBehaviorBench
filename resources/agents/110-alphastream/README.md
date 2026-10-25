# AlphaStream deployment

This unit packages the LangGraph multi-agent stock-analysis app
[`lc2panda/alphastream`](https://github.com/lc2panda/alphastream) pinned at commit
`abc3398c49ac2ad0ff3be34ca787b03c67004ead`.

## Source policy: bundled

Upstream declares a git submodule:

```text
[submodule "app/tradingagents"]
    path = app/tradingagents
    url = https://github.com/TauricResearch/TradingAgents.git
```

The gitlink is pinned to `2ca6a3acda193a246c3774a9369a255c5bf9d56f`, which no
longer exists in `TauricResearch/TradingAgents` (the project's history was
rewritten; `upload-pack: not our ref`). Because of that:

- `source.method = "git"` is rejected by ABB ("Git source contains submodules").
- A recursive clone cannot restore the pinned submodule, and every revision of
  `lc2panda/alphastream` in the available history pins this same commit.

The submodule content is **not required** by this integration: the binding and
the evaluated code paths live in `app/` and do not import `app/tradingagents`.
A smoke run and a KUMA Case both completed with an empty/missing
`app/tradingagents` directory (17 framework spans, 11 model requests, no egress
denials). The unit therefore ships as `method = "bundled"`.

## Restoring source

Before running this unit, place the matching source tree under `agent/`
(the directory is ignored by Git and is not committed):

```bash
git clone https://github.com/lc2panda/alphastream.git /tmp/alphastream
git -C /tmp/alphastream checkout abc3398c49ac2ad0ff3be34ca787b03c67004ead
rm -rf /tmp/alphastream/.git /tmp/alphastream/app/tradingagents
cp -R /tmp/alphastream/. <this-unit>/agent/
```

Do not initialize the `app/tradingagents` submodule: its pinned commit is gone,
and the integration does not need it. If a future deployment needs the
submodule content, vendor `TauricResearch/TradingAgents` at a reachable revision
and document the exact revision here.

## Runtime

- Model: OpenAI-compatible endpoint via ABB interception (`OPENAI_API_KEY`);
  `OPENAI_API_MODEL` is set from `LLM_MODEL` by the binding.
- The binding maps plain-text input to `(stock_code, market_type)` and runs the
  analysis graph with `research_depth=3`.
- Market data comes from akshare/eastmoney providers; without reachable
  providers the analysis degrades and must say so rather than invent data.
