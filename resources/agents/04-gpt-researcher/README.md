# GPT Researcher in ABB

Official source: https://github.com/assafelovic/gpt-researcher
Revision: `6f998577d547b1e54ec662dac63583aa11e3b84b` (downloaded 2026-09-14).
Matches Wangyi's recorded source revision. MIT license retained in `agent/`.
Upstream code is unchanged; `agent/abb-langgraph.json` identifies the real native
class. The required ABB binding wraps the Python researcher in one LangGraph node,
so the registry's framework describes the ABB execution boundary, not an upstream
claim that GPT Researcher itself is a compiled LangGraph.

The native `GPTResearcher.conduct_research()` and `write_report()` perform research
and report generation. This deployment uses its official arXiv retriever and a
CPU-local `sentence-transformers/all-MiniLM-L6-v2` model, pinned to revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41` at image build. It needs no Tavily or
embedding API key. Kuma and the shared model provider still require credentials.

This is an explicitly limited academic-research configuration: arXiv sources,
three results per query, one research iteration, target 500 words. The native
search operation is wrapped only to observe its real query/result; report writing
is unchanged. Callback configuration stays inside the container. Public HTTP(S)
egress is restricted to arXiv API and paper paths, with model routes separate.

Each invocation receives its Case's ordered conversation, including prior final
reports. GPT Researcher creates a fresh research instance; no cross-Case state is
reused. No earlier sources are represented as newly verified evidence.

Status: **adapting**; real certification is pending a valid OpenRouter key.
See [the campaign](../../../docs/Benchmark-Repair-Campaign.md) for onboarding results.

```bash
agentbench evaluate gpt-researcher --cases 1 --max-steps 1 --yes --no-view
agentbench certify gpt-researcher --cases 1 --yes --no-view
```
