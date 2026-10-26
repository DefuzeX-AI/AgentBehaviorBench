# OntoCast onboarding evidence and remaining gate (#501)

Source: `growgraph/ontocast@b111d53f722fa6b3fc17091188c3135c6c54acc2`; ABB base `8349406ee5bdc4e8b22e220a89236bab10a6bcef`.
Model: `deepseek/deepseek-flash`. This is a draft for review. Runtime execution and a separate
hash-verified LocalProvider assessment are verified; the end-to-end CLI quality
gate is still failed. A final rerun was blocked by upstream HTTP 402 balance.
This is not full Step 1 acceptance. No GT exploration or official KUMA
Case/Judge call is claimed.

Before submission, main `0d59f2585c8ef38fbf0bc1d4e45dd8e362e8536d` was merged to retain the current Klaatcode
registration and unrelated launcher changes. The execution used the ABB base
above; the incoming changes did not touch ABB core or this Agent unit.

## Behavior and outcome

One complete synthetic English document described Aster Research, its laboratory,
researcher and project. The unmodified native LangGraph extracted ontology and
facts using its own model calls, loops, critics and validation. The binding follows
the native `make_ontocast_node` / `text_in_turtle_out` example, retaining callbacks
and owned ToolBox lifecycle. It does not replace extraction with a new Agent.

- Suite: `suite_eadb0f44c2ba4050a0a5c247707fa9f9`.
- SDK run: `68e7e63d88954de08098165d3af6e792`; artifact attempt: `427a6d573c104e649c4395854d99ade2`.
- One Case / one input; original CLI 1, 258.22 seconds.
- Execution `succeeded`, trace validation `succeeded`,
  cleanup `succeeded`. Original Judge delivery failed: its 8192 output tokens
  were all reasoning, so no JSON report was available. Original quality gate failed.
- A separate unmodified LocalProvider assessment of identical hash-verified
  complete evidence returned **pass/high**
  with no issues or evidence gaps, using 32768 output tokens and official JSON mode.
  Original prompts, response bytes, validator and execution records were unchanged.
  That supplementary result does not overwrite the original CLI failure.
- Interceptor counts: `{"interceptor_ready": 2, "llm_request": 4, "llm_response": 4}`.
- Saved native ontology/facts parse as Turtle: 177 ontology
  triples, 80 facts triples. Expected named entities were present.
  This fixture inspection is not exhaustive correctness/coverage certification.
- 14 focused binding tests passed, including invalid input/hidden-state rejection,
  live callback forwarding, shared sync-loop ownership and cleanup after failure.
- Clean Git-source restoration and binding load passed. All 514 source blobs
  matched the pinned upstream Git object hashes; native source is ignored.

## Deployment scope

The native Fuseki manager runs with pinned Jena 6.0.0 / Java 21 inside each
Case container: loopback-only, fresh workspace TDB2 datasets, ephemeral local
authentication and a 128 MiB JVM heap. The outer binding owns process startup,
readiness and shutdown, including failure cleanup. There is no host port or
external database/vector server. Config.in_memory supplies no-vector defaults;
supported Fuseki URI/auth settings select the native Fuseki manager. Entity
consolidation remains enabled with real sentence-transformers 6.2.0 and CPU
torch 2.14.1+cpu. Supported aggregation/chunking/embedding settings select one
shared all-MiniLM-L6-v2 checkpoint; cached snapshot(s):
`1110a243fdf4706b3f48f1d95db1a4f5529b4d41`. This differs from native multilingual
defaults and is an English-text deployment. No fake embedding, native patch,
removed tool or disabled aggregation is used.

The disconnected offline startup/embedding check passed as UID 10001 under
1 GiB / 1 CPU / 128 PID / read-only root constraints. The final Python process
max RSS was 638368 KiB, excluding the Java subprocess; this is not a full-run
container peak. Native RDF 1.2 writes and HTTP export with independent pyoxigraph
parsing also passed. The real ABB run retains standard worker isolation.
The host controller used WSL root for
cross-UID artifact cleanup; Agent/SDK workers remain nonroot.

Only native openai/documents extras and required CPU embedding dependencies are
installed. Full OCR/document conversion and hdbscan/umap segmentation extras are
absent; native naive segmentation fallback is recorded. No external seed ontology,
vector retrieval, GUI, browser, general coding/shell tool or messaging account is
provisioned. Inputs are independent complete documents, not implicit chat history.

ABB replacement interception selects the actual model. The final host-only
local-Judge transport enables DeepSeek thinking with a 32768-token output budget and JSON mode;
the local evidence cap is 4M characters. Original Judge messages, system prompt,
response bytes and response validation are unchanged. It does not process Agent
traffic, and the transport source is included with the public evidence. Earlier
non-thinking / 2048-token Judge attempts are retained separately.

## Failed attempts retained

1. v1 blocked before Agent/model activity: missing worker `opentelemetry`.
   The outer Docker packaging now installs SDK trace dependencies explicitly.
2. v2 made four real successful model calls with accepted trace and cleanup,
   then the input failed because native entity consolidation required the missing
   sentence-transformers dependency. The local Judge was inconclusive; no pass
   was claimed. The real CPU encoder was provisioned before the later attempt.
3. v3 was interrupted: WSL uptime reset and the controller/worker disappeared
   before a final result. Its partial ledger has three requests and two responses;
   its outcome is unknown and excluded from acceptance.
4. v4 made four real model calls but native pure in-memory serialization rejected
   an RDF 1.2 provenance triple term; input failed, Judge inconclusive. An offline
   plain-versus-provenance diagnostic reproduced the incompatibility. Selecting
   the supported native Fuseki deployment preserves provenance and native code.
5. v5 made zero Agent model calls: the split outer helper was not on ABB's import
   path. The helper now lives in the single binding file. Its failure is retained.
6. v6 was blocked by upstream HTTP 402 insufficient balance on the first Agent
   inference request; input failed and Judge inconclusive. The user replenished
   the account before the subsequent attempt. This is an infrastructure failure.
7. v7 completed Agent execution, trace validation and cleanup, but its local
   Judge exceeded the 1.2M-character limit (CLI 1). Two Judge-only replays used
   identical hash-verified evidence at 4M characters. Both returned an invalid
   `pass` with evidence gaps; the unchanged validator rejected both. Neither is
   acceptance. The Case had no Agent context. The final Case keeps the same
   document payload and includes the actual deployed Profile using ABB's normal
   `load_agent_context` / `abb_agent_context` contract, with a 4M-character limit.
   Original and final Cases, failed Judge replies and original runs are retained.
8. v8 again completed Agent execution/trace/cleanup, but the non-thinking Judge
   returned invalid pass-with-gaps (CLI 1). A separate hash-verified full-evidence
   replay with thinking enabled and 8192 output tokens returned validated pass/high.
   The original CLI result and raw reply were not edited. The final attempt uses
   those proven Judge options end-to-end, without changing native Agent traffic.
9. v9 completed execution/trace/cleanup but its Judge used all 8192 output tokens
   for reasoning (finish reason length), producing no JSON (CLI 1). A separate
   full-evidence replay at 32768 output tokens with official JSON mode returned
   validated pass/high. A fresh end-to-end attempt then used that configuration.
10. v10 was blocked on the first Agent request by upstream HTTP 402 insufficient
   balance (CLI 1, Judge inconclusive). Paid requests stopped. No final end-to-end
   CLI success is claimed. Human review of the deployment/evidence and a later
   funded final acceptance run remain before this PR is ready for merge.
11. A build was interrupted while recursively assigning ownership over the model
   cache. Outer Docker packaging now assigns only writable directory roots.

No failure above is submitted as a GT defect. Each runtime attempt is separate;
earlier evidence and Case content were not overwritten.

## Evidence and reproduction

- [Sanitized evidence ZIP and SHA-256](https://github.com/Sam-Hui-dot/AgentBehaviorBench/releases/tag/issue501-onboarding-20261027).
- ZIP SHA-256: `7f71cb7b1db5969afd10c98adaa76fbd9c63a26352cf80b56452ac2c8734c29f`.
- Exact input: [smoke-case.json](smoke-case.json).
- [Contributor summary](acceptance-summary.json); original SDK records and export
  hashes are in the archive. Copied manifest attachment digests refer to originals.
- These are labeled sanitized derivatives, not a full importable SDK ledger.
  Original raw artifacts remain locally retained; credentials/private model
  reasoning are excluded. The file/profile contains all material deployment limits.

Equivalent fixed-input acceptance command for the pending final run:

```sh
ABB_LOCAL_JUDGE_MAX_CHARS=4000000 python -m agentbench evaluate ontocast --sdk local \
  --registry resources/registry.toml --case-file /path/to/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 900 \
  --no-view -y --results-dir /path/to/fresh-results
```

Configure the selected Agent model and the Judge-only transport documented above
before running this command. The evidence archive includes the exact runner and
transport source; the standalone CLI command does not itself install the host
transport (thinking enabled, max_tokens 32768, JSON mode). The imported Case includes the
deployed Profile in abb_agent_context.

The registry remains `enabled=false`, `status=adapting`. Integration, execution,
local Judge, upstream merge and subsequent GT acceptance are distinct stages.
