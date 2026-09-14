# GPT Researcher in ABB

Official source: https://github.com/assafelovic/gpt-researcher
Revision: `6f998577d547b1e54ec662dac63583aa11e3b84b` (downloaded 2026-09-14).
Matches Wangyi's recorded source revision. MIT license retained in `agent/`.
Upstream code is unchanged; `agent/abb-langgraph.json` identifies the real native
class. The required ABB binding wraps the Python researcher in one LangGraph node,
so the registry's framework describes the ABB execution boundary, not an upstream
claim that GPT Researcher itself is a compiled LangGraph.

The native `GPTResearcher.conduct_research()` and `write_report()` perform research
and report generation. This deployment uses its official PubMed Central retriever and a
CPU-local `sentence-transformers/all-MiniLM-L6-v2` model, pinned to revision
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41` at image build. It needs no Tavily or
embedding API key. Kuma and the shared model provider still require credentials.

This is an explicitly limited biomedical-literature configuration: PubMed Central full text,
one article per query, one research iteration, target 500 words. The native
search operation is observed with its actual query/result. The binding uses NCBI's
equivalent form POST for search URLs above 2000 encoded bytes, retaining the native
parameters, article IDs, full-text fetching and parsing. Report writing remains
in the native researcher. Callback configuration stays inside the container. Public HTTPS
egress is restricted to NCBI E-utilities search/fetch paths, with model routes separate.
The earlier arXiv setup failed native public searches with HTTP 429; switching
between HTTP and HTTPS did not resolve the native query. PMC returned actual
article full text without another API key. Source lists are returned unchanged,
including empty lists for the Judge to assess. This is literature research, not clinical advice.
NCBI requests are serialized within each Case with a 1.1-second cooldown after
every request, including failures. The campaign uses at most three Case workers
with this keyless deployment to respect the shared 3 requests/second allowance.
The image preloads cl100k_base, o200k_base and gpt2 tokenizer data; runtime does
not need an extra download domain. The container check verifies these offline.

Each invocation receives its Case's ordered conversation, including prior final
reports. GPT Researcher creates a fresh research instance; no cross-Case state is
reused. No earlier sources are represented as newly verified evidence. Its native
agent selection, query planning and report writing see the full conversation.
The upstream research planner also searches the original task verbatim; for this
raw-task fallback, the observed retriever uses the current user question instead
of sending the complete conversation to NCBI. Model-generated search phrases are
unchanged. Recorded tool arguments show the actual search term.

This separation fixes multi-turn HTTP 414 errors without dropping model context.
The long-query POST route is limited to `/entrez/eutils/esearch.fcgi`; it does not
allow POST to EFetch, EPost or arbitrary endpoints. See the official
[NCBI ESearch parameters](https://www.ncbi.nlm.nih.gov/books/NBK25499/).

Status: **ready** after real certification on 2026-09-14. Native PubMed full-text
research was also verified separately; certification and mixed-suite findings
remain recorded in the campaign, including out-of-scope generated Cases.
See [the campaign](../../../docs/Benchmark-Repair-Campaign.md) for onboarding results.

```bash
agentbench evaluate gpt-researcher --cases 1 --max-steps 1 --yes --no-view
agentbench certify gpt-researcher --yes --no-view
```
