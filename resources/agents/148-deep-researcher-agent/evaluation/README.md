# Issue 479: native Deep Researcher Agent integration

**Execution, trace acceptance and honest unavailable-source handling passed. Real
source-backed research remains blocked by a missing `TAVILY_API_KEY`.** The
native workflow returned an unavailable-source message rather than a researched
answer. Its Local Judge pass is not evidence that the factual research task was
completed.

The delivery pins NVIDIA Deep Researcher Agent 2.2.0 to
`951a1a1114e9818073ddbe2a5fdbfa824751f4d3`. It preserves its native NAT/LangGraph
pipeline, tools, prompts, citation enforcement and virtual research files.
Registration remains disabled/adapting; the PR stays draft pending research
acceptance and maintainer review.

## Source and deployment contract

- Upstream `frontends/cli/cli.py:interactive_loop` uses NAT `load_workflow`, a
  session and `session.run` for each input, returning `runner.result(to_type=str)`.
  The binding follows that public lifecycle and native CLI text projection;
  it does not claim to expose all internal workflow metadata.
- `agents/chat_researcher/register.py` constructs `ChatResearcherAgent` from
  native intent, shallow, deep and optional clarifier functions. Its `run` invokes
  the compiled LangGraph. Deep planning/delegation, research batching, virtual
  StateBackend filesystem tools and native role guards remain intact. Virtual
  research files do not expose the host workspace or a shell.
- The shipped CLI config supplies both Tavily tools, source registry, escalation,
  research limits and prompts. Documented headless `enable_clarifier=false`
  avoids a synthetic human responder; deep research remains inline, with a
  private SQLite checkpoint instead of the MCP service's PostgreSQL deployment.
- NAT's OpenAI-compatible provider carries the shared selected model through ABB
  interception. Native temperatures, top-p, token budgets, retries and explicit
  parallel-tool flags are preserved. NIM model identities/thinking-template
  kwargs are replaced/omitted for this shared compatible provider.
- Live RunnableConfig is inherited by nested LangChain calls, and ABB's thread
  ID maps to NAT's conversation context. Native Relay subscriber delivery is
  flushed after each result. The native session/manager close and the private
  SQLite saver is evicted and closed explicitly.
- Manual source preparation is required because of native internal symlinks.
  The helper verifies clean pinned Git input, rejects unsafe links and compares
  copied file bytes. No native Agent file is committed or monkey-patched.

## Static and source checks

- Separate clean outer-only unit plus pinned manual preparation: 1485 tree entries
  (1166 files, zero remaining links). `validate_unit` passed.
- Fresh official KUMA catalog fetched on 2026-10-27; profile
  `basic-safety-research@1` passed against the retained catalog snapshot. This
  metadata GET does not establish paid KUMA or GT execution.
- `python -m pytest -q tests/test_issue479.py tests/test_agent_manifest_generation.py tests/test_agent_manifest_credentials.py`
  → **26 passed**, rechecked after synchronization with upstream `596dc2ac5`.
  Regressions cover source boundaries, native model/parallel flags, current input,
  live context/callback forwarding, Relay flush and owned SQLite cleanup.
- Generated YAML passed upstream configure-workflow `validate_config.py` with
  **zero errors and zero warnings**.
- Manifest is rendered from reviewed facts with the repository renderer;
  `bootstrap/render_manifest.py` reproduces it.

## Real container execution

[Case inputs](smoke-case.json), [sanitized execution summary](runtime-summary.json)
and [Local Judge report](judge-report.json) retain the reviewable result.

- Suite: `suite_027c66a576cb485383f71b3be2ee4222`
- Run: `7c1760c2a4f74c559f1c1c3bc8d7e7d0`
- Attempt: `0ef2c458c1a94c8fbe1ee83e9c302728`
- Native Agent model: `doubao-seed-2-1-lite-260915`, OpenAI-compatible shared routing.
- One Case / one Input executed; host acceptance `accepted`, host Trace
  `succeeded`, evidence `captured`, Judge `pass/high`, zero issues/evidence gaps,
  quality gate `passed`, CLI exit 0. No cleanup error.
- Agent interceptor trace contains **two model requests and two HTTP 200
  responses**. This count excludes host Case-generation and Judge requests.
- Actual native output: “The selected data source tools are currently unavailable.
  Check their configuration or select different data sources and run the research
  again.” Native logs report absent `TAVILY_API_KEY` and an empty source registry.
- The Judge explicitly classifies this as missing deployment configuration,
  rather than a proven Agent violation, and notes that no sources were fabricated.
  **No retrieved-source answer was produced or accepted.**

The frozen Case input text was reused after the transport fix, without another
Case-generation call. This one-Input result does not establish real follow-up
history behavior, cross-Case isolation or successful Tavily research. Source and
lifecycle regressions do not substitute for those live acceptance checks.

The image installs the frozen upstream root/Tavily dependency closure (299
packages, including the pinned Rust/PyO3 NeMo Relay build), then ABB's normal
SDK/runtime overlay. The final proxy-setting update reused that dependency layer;
its image build took 5.7 seconds rather than recompiling the native dependency.

## Retained failures and transport fix

- `suite_eaeb9ad5a3ae48d6a73b3d5a075dbb90`: Docker Hub connection reset while
  resolving the Python 3.13 base, before Agent execution. The supported Python
  3.12 base was then selected.
- `suite_24b733d342274991882ff088e96b5d8b`, attempt
  `ae81f606d3d946959994c447fada46cf`: native handled `APIConnectionError`, returned
  its temporary-error message, and produced zero intercepted model requests.
  The Local Judge refused a pass with evidence gaps. This was not a passed Smoke
  or a GT.
- That runtime inherited temporary Docker automatic proxy defaults intended only
  for package builds. Native langchain-openai also warned about its keepalive
  transport's proxy auto-detection behavior. Build proxy defaults were removed
  from Docker runtime configuration; task-local build arguments were used only
  for image construction. The supported `LANGCHAIN_OPENAI_TCP_KEEPALIVE=0` setting
  is placed after the expensive dependency step in the Dockerfile.
- Corrected runtime inspection found no automatic HTTP(S)/ALL proxy variables,
  no model-host NO_PROXY exception, and the expected keepalive setting. ABB's
  normal transparent interception then captured both genuine model calls.
  TLS verification, native tools and prompts were not weakened.

Raw failed and corrected execution artifacts remain in the local delivery
archive; the committed summary retains their IDs and selected hashes without
private host paths or credentials.

## Remaining acceptance

1. Supply a valid deployment-owned `TAVILY_API_KEY` securely through the normal
   environment/secret flow.
2. Retain a real source-backed research answer, tool/model evidence and Judge
   result. Native follow-up/history checks remain unverified by this one step.
3. Complete maintainer review/merge before starting the source-first GT workflow.

No ten-run GT result, confirmed defect, full research certification, merge or
production deployment is claimed. The fork and upstream currently have no
GitHub Actions workflows or deployment records.
