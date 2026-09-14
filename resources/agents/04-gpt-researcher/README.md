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
one article per query and one research iteration. The supported
`write_report(custom_prompt=...)` option requests at most 500 words including
references (or a shorter user limit). Native `TOTAL_WORDS` means a minimum,
so it is not used as a maximum. The returned report is never truncated; actual
length and citation quality remain visible to the Judge. The native
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

Each invocation receives only the current question. The first Input runs native
research and report writing, then saves the unchanged question and report through
`POST /api/reports`, following the upstream frontend's save-report workflow.
The binding retains the returned opaque report ID. Later Inputs send only
`{"role":"user","content":current_question}` to
`POST /api/reports/{id}/chat`. The original server's `ReportStore` appends the
chat history; `ChatAgentWithMemory` selects report passages and sends its native
history to the model. BBA does not build history, summarize reports or rewrite
search queries. Chat responses and native tool metadata are returned unchanged.

One Case owns one isolated instance of the unchanged native FastAPI app, loaded
from its original source into a unique module, and a private native report-store
file. The supported `REPORT_STORE_PATH` setting is scoped to app construction.
Closing the Case drops that app and deletes its files. HTTPX's in-process ASGI
transport invokes the original routes without opening a listening port. The
frontend files remain in the image because the original app mounts them on import;
the frontend/export web-server lifespan is not started by this API-only binding.

The native chat route constructs `Config("default")`. Docker uses the supported
`EMBEDDING`, `EMBEDDING_KWARGS` and `*_LLM` environment settings to match research
configuration and use the preloaded local embedding model. Real LangGraph node
context carries the current callbacks into native retrieval, model and tool calls.
No Tavily key is supplied: native `quick_search` remains visible but returns its
original disabled-search error. Chat can discuss the saved report; it cannot
start a new PMC search through that tool.

This is the upstream report-chat memory behavior, with its actual limitations.
The saved research question is a separate report field, not automatically a chat
message. A first-question constraint missing from the report may not reach chat.
The native app retrieves report chunks, not the underlying full papers; later
chat turns are retained natively without BBA compression or cross-Case sharing.
The 500-word custom prompt applies to the initial research report only. Follow-up
responses use the unmodified native chat prompt.

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

Earlier current-input certification on 2026-09-14 completed one real Input and
received an official Judge report. The Judge verdict was
`issue` for incorrect/unverified citations and a mismatched PMC article title,
with no evidence gaps. This certifies execution, not citation accuracy or
conversational recall. See
[the live record](../../../docs/Agent-Owned-Context-Live-2026-09-14.json).

The new native report-chat deployment is **adapting** until real certification
completes. The earlier research-only certification does not certify this API.

```bash
agentbench evaluate gpt-researcher --cases 1 --max-steps 1 --yes --no-view
agentbench certify gpt-researcher --yes --no-view
```
