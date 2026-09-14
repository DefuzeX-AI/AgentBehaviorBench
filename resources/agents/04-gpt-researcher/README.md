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

Each invocation receives only the current research question. GPT Researcher
creates a fresh research instance through its native research/report entrypoint;
prior turns and reports are not packed into the query or search term. Native
agent selection, query planning and report writing see the same current query.
The binding does not replace native search phrases or implement chat routing,
summaries, report memory or `ChatAgentWithMemory` on the Agent's behalf.

The Case container stays alive across Inputs, but this exposed task entrypoint
does not promise conversational memory. Testing several Inputs measures repeated
research-task execution, not successful use of the upstream report-chat feature.
The native Agent may own writable files; BBA does not read them to reconstruct
history or share them with another Case.

Long standalone queries still use NCBI's supported form POST to avoid HTTP 414.
The long-query POST route is limited to `/entrez/eutils/esearch.fcgi`; it does not
allow POST to EFetch, EPost or arbitrary endpoints. See the official
[NCBI ESearch parameters](https://www.ncbi.nlm.nih.gov/books/NBK25499/).

Historical status: **ready** after real certification on 2026-09-14. Native PubMed full-text
research was also verified separately; certification and mixed-suite findings
remain recorded in the campaign, including out-of-scope generated Cases. Those
results used the old history-replay binding; they do not certify the new
current-input behavior. Current readiness is recorded in the registry.
See [the campaign](../../../docs/Benchmark-Repair-Campaign.md) for onboarding results.

Current-input certification on 2026-09-14 completed one real Input and received
an official Judge report; the registry is now **ready**. The Judge verdict was
`issue` for incorrect/unverified citations and a mismatched PMC article title,
with no evidence gaps. This certifies execution, not citation accuracy or
conversational recall. See
[the live record](../../../docs/Agent-Owned-Context-Live-2026-09-14.json).

```bash
agentbench evaluate gpt-researcher --cases 1 --max-steps 1 --yes --no-view
agentbench certify gpt-researcher --yes --no-view
```
