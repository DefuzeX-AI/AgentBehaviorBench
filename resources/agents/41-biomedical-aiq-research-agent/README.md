# NVIDIA Biomedical AI-Q Research Agent (ABB unit)

Upstream: [NVIDIA-AI-Blueprints/biomedical-aiq-research-agent](https://github.com/NVIDIA-AI-Blueprints/biomedical-aiq-research-agent) at `b5cd7b4c7ae544c1e21ac79ef9fa67641eeff5a4`, Apache-2.0. The source snapshot under `agent/` is unmodified. This unit is associated with [AgentBehaviorBench issue #229](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/229).

## What runs

`bindings/bridge.py` invokes the upstream `ai_researcher` entry function with the same NeMo Agent Toolkit `WorkflowBuilder` lifecycle used by upstream tests. That entry function runs the native query-planning and report-generation LangGraphs. Plain ABB text supplies the research topic and uses the explicit deployment context (including topic-neutral report constraints) in `[adapter.context]`; strict JSON text can supply all six native business arguments. The output is the native final report.

## Required deployment

- An OpenAI-compatible target model selected by ABB. The native planning/reflection parsers require `</think>` followed by JSON in response **content**; a separate `reasoning_content` field alone is insufficient. The supplied operator routing files select hosted `nvidia/nemotron-3-super-120b-a12b` for the native `ai_researcher` workflow without changing the Local Judge's existing DeepSeek configuration. Its API returned HTTP 200, but only a real adapted request and fresh container run can prove compatibility and acceptance.
- A reachable NVIDIA RAG `/generate` endpoint and existing collection named by the Case. This unit defaults to the authenticated local bridge at `http://host.docker.internal:8081/v1`; the bridge currently serves the one-paper `Biomedical_Dataset` collection only. Start it with `scripts/start_biomedical_rag_api.py` and set a distinct `RAG_API_KEY` in `.env`. Keep cloud ingress to host port 8081 closed. A custom `AIRA_RAG_URL` requires its exact host/path in `agent.toml`.
- Optional `TAVILY_API_KEY` for web fallback.
- Optional `NVIDIA_API_KEY` plus MolMIM and DiffDock endpoints for virtual-screening requests. Public hosted endpoints are the upstream defaults.

The binding installs a value-based log filter because the pinned upstream virtual-screening helper logs `NVIDIA_API_KEY`; no secret value is committed or intentionally retained in ABB output.

## Validation status

The one-PDF native NV-Ingest ingestion and NVIDIA RAG retrieval infrastructure check passed (61 text/table elements; three sourced retrieval hits). Real Docker Agent execution with hosted Nemotron 3 Super and the explicit streaming response adapter completed 1/1 with a complete 53-span input Trace. The Local Judge returned `issue` because the native research report did not satisfy the generic self-introduction input. The Local quality gate failed; maintainers are being asked to clarify the smoke acceptance criterion in [Issue #229](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/229#issuecomment-5983125813). The submitted registry entry remains disabled and `adapting`; enable this Agent explicitly when testing. Execution completion is not quality or official KUMA acceptance.

## Native NVIDIA model check and Local re-run

The original 49B-v1 hosted probe returned HTTP 410 on 2026-10-05. NVIDIA's
model pages mark both [49B v1](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1)
and [v1.5](https://build.nvidia.com/nvidia/llama-3_3-nemotron-super-49b-v1_5/deploy)
free endpoints deprecated. The current routing selects Nemotron 3 Super instead;
the pinned native model alias/prompts and research workflow remain unchanged.
To inspect the account's live catalog (GET only):

```bash
python scripts/check_biomedical_reasoning.py --list-models
```

A listed model is only a candidate, not proof of inference or parser compatibility.
The manifest explicitly selects `openai-chat-thinking`, an interceptor wire
that moves streamed `reasoning_content` into `<think>…</think>` in `content` before
the real answer. It does not invent reasoning, queries or reports. With no
reasoning it does not manufacture delimiters; unsupported tool-call/mixed-format
responses and interrupted streams fail visibly. Ordinary `openai-chat` stays
pass-through, and this opt-in wire has no automatic recognition signature.
Fresh `network.jsonl` keeps the raw upstream payload and a separate converted
`client_payload`, tagged `response_adapter=reasoning-content-to-inline-v1`.
Non-streaming responses stay unchanged: native intention/relevancy checks parse
their answer content directly as JSON. Run `suite_30ff02b59234454d92d9eb47eb057795`
failed because the earlier adapter also prefixed unary JSON with thinking text;
the corrected adapter is streaming-only. Run
`suite_a526d4bb1822430f955ff0ce0032700d` completed and was host accepted after
this fix; Judge still found the report off-topic for the generic introduction
Case. This is not a passed behavioral gate or an official KUMA finding.

### Trace verification

The binding now uses a public LangChain RunnableLambda around the unchanged
Toolkit runner to propagate only observer callbacks into the native graphs.
Business input/configuration and exception/cleanup behavior remain unchanged.
ABB keeps local correlation IDs and payload paths in its original JSONL records
while emitting SDK-facing semantic spans with observed model/tool content.
The SDK worker declares only public resource metadata. SDK redaction, capture
budgets and privacy rules remain active; forbidden external attributes and
unfinished calls still produce degraded/error evidence.

Real Docker Local run `suite_3ff7297791b5467d968b13f918c673cd` verified this
boundary with the pinned native Toolkit: 53 SDK spans, per-input traces complete,
zero dropped/unfinished spans and no truncation or capture reasons. All 13 model
spans include captured input/output; five RAG calls returned HTTP 200. Native
planning, research, reflection and finalization nodes are recorded. Judge still
reported the research report off-topic for the generic self-introduction Case;
execution/Trace completeness does not mean the quality gate passed.

For every subsequent run, check `evaluation/manifest.json` **steps'
capture_status.traces**, `evaluation/inputs/0001/evidence.json` spans/reasons,
and network/framework correlation. Manifest-level `otel: complete` alone only
proves lifecycle completion. The Local evidence does not replace official KUMA
acceptance or validate unexercised capabilities such as full virtual screening.

From the ABB repository root, first run this one-request hosted inference check:

```bash
source .venv/bin/activate
python scripts/check_biomedical_reasoning.py --adapt-reasoning
```

It uses the pinned upstream query prompt and reasoning settings, prints no key
or reasoning text, and makes no retries (up to 5000 output tokens). Proceed only
if `adapted_query_contract_passed` is true; the raw `native_query_contract_passed`
can remain false because it describes the unconverted response. This is still
not an ABB acceptance. The script uses the exact same adapter as the interceptor.
With the RAG bridge running, use the routing files for this command only:

```bash
ABB_MODEL_PROVIDERS_CONFIG="$PWD/resources/biomedical-model-providers.toml" \
ABB_MODEL_ROUTING_CONFIG="$PWD/resources/biomedical-model-routing-nvidia.toml" \
agentbench evaluate biomedical-aiq-research-agent --cases 1 --sdk local --no-view
```

Do not overwrite DeepSeek keys/models or set `--model` to the NVIDIA model for
this split deployment. The provider priority remains unchanged; the Local Judge
uses its existing provider or explicit `ABB_LOCAL_JUDGE_*` overrides. The Agent
target mounts `NVIDIA_API_KEY` into the interceptor and still receives an isolated
token for `OPENAI_API_KEY`. NVIDIA virtual-screening credentials remain separate
optional tool credentials. Verify actual Agent/Judge models in fresh artifacts.
The changed manifest and interceptor source may rebuild both images. If
`DEFUZEX_MODEL_INTERCEPTOR_IMAGE` selects a prebuilt image, it must include the
new wire; an old image will reject the unknown protocol rather than bypass it.

Onboarding is incomplete: `requirement.md` still needs an explicit strategy group
selected from the authenticated current KUMA catalog. Offline parser acceptance
does not validate a live catalog selection. Native NVIDIA-model execution and
Local Trace capture have been verified; Local smoke gate confirmation, PR
review and official KUMA evaluation remain pending.
