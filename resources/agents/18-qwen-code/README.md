# Qwen Code through native ACP

This unit uses unmodified [Qwen Code v0.24.2](https://github.com/QwenLM/qwen-code/tree/1026c4a50f4a32f77da98bdacfba2e5faa8cc70a),
commit `1026c4a50f4a32f77da98bdacfba2e5faa8cc70a`. It reuses ABB's shared
`ACPAdapter`; there is no replacement Agent implementation or upstream patch.
The shared adapter's optional evidence-reader hook forwards completion metadata
without interpreting it; existing single-argument readers remain compatible.
Readiness is tracked in [the registry](../../registry.toml).

This integration was prepared by source/configuration analysis and offline
synthetic evidence checks only.
No dependencies were installed, Docker image built, Qwen process started, model
called, full integration suite run, or certification performed. Do not treat this document
as a runtime acceptance result.

## Configuration

Set these in your host environment or the root private `.env` (never commit it):

```dotenv
QWEN_API_KEY=your-provider-api-key
QWEN_MODEL=qwen3-coder-plus
QWEN_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1
```

`QWEN_API_KEY` and `QWEN_MODEL` are required. The model above is an example,
not a default or a guarantee of account availability. Choose a model supporting
Chat Completions, streaming and tool calls. A blank/missing `QWEN_BASE_URL`
uses the China DashScope compatible-mode base URL above. Keys, models, billing
plans and regions must match; OAuth/browser login is not part of this profile.
No OpenRouter, Claude or MiniMax credential is implicitly reused.

The declared HTTPS model routes support:

| Provider profile | `QWEN_BASE_URL` |
| --- | --- |
| DashScope China | `https://dashscope.aliyuncs.com/compatible-mode/v1` |
| DashScope international | `https://dashscope-intl.aliyuncs.com/compatible-mode/v1` |
| DashScope US | `https://dashscope-us.aliyuncs.com/compatible-mode/v1` |
| Coding Plan China | `https://coding.dashscope.aliyuncs.com/v1` |
| Coding Plan international | `https://coding-intl.dashscope.aliyuncs.com/v1` |

These routes come from upstream provider code/tests and model-provider docs;
account entitlement and endpoint availability have not been checked. The
launcher checks the resulting `POST <base>/chat/completions` against `agent.toml`.
It rejects HTTP, URL-embedded credentials, query/fragment components and
undeclared endpoints before launching Qwen. Trailing slashes are normalized.

For another compatible gateway, add its **exact** host, port and completion
path to `llm_interception.routes` with `protocol_plugin = "openai-chat"` and
`credential = "qwen-api-key"`, then set `QWEN_BASE_URL`. Keep the native wire
API and route consistent. Do not add broad tool egress or disable interception
or TLS verification to work around a missing model route. Responses,
Anthropic, Gemini and OAuth profiles require separate integration review.

ABB observes this Agent's native model traffic; `--model`/`OPENROUTER_MODEL`
does not select Qwen's native model. Use `QWEN_MODEL`. Evaluation Case/Judge
services have their own credentials and configuration.

## Source and build

`agent/` contains the unmodified upstream source snapshot at the commit above,
vendored as ordinary files in ABB. Its nested `.git` directory was removed;
it is not a submodule and a fresh ABB clone already includes the source.
`source-manifest.json` records its repository and exact revision.

For future source updates, verify a separate clean upstream checkout against
the intended revision before replacing this snapshot. Do not reset or overwrite
existing user changes. No host Qwen installation, login state, home directory
or node_modules is copied in.

The Dockerfile follows the pinned upstream release packaging: Node 22 with
the upstream image digest, Corepack using the integrity-pinned packageManager
(`pnpm@11.24.0`), frozen lockfile, native CLI-only workspace build, bundle,
native package preparation and installation of that generated package. The
CLI-only option still builds its runtime assets; it skips unrelated IDE/live
integrations. Native dependency patches declared by upstream remain intact.
The global `qwen` entry point retains the original launcher and GC behavior.

Build through ABB, which stages `.abb-runtime` and injects the pinned ACP and
selected SDK dependencies. A raw `docker build` of this unit alone is missing
those overlays. The final runtime is a non-root Linux container; root-owned
Agent installation files are separate from its writable home/workspace.

## Deployment behavior and boundaries

- The outer Python launcher writes native settings to a fresh private
  `QWEN_HOME` for each ACP process. Settings reference `QWEN_API_KEY` by name;
  the key is neither stored in settings nor passed as a CLI argument.
- Auth and model selection are explicit (`openai`, `chat-completions`). The
  original prompts, model responses, tool definitions and Agent loop are used.
- Only the configured Case workspace is pretrusted using native
  `trustedFolders.json`; the trust gate is not globally disabled. The workspace
  initially has no target project, apart from ABB bookkeeping.
- Native approval mode remains `default`. ABB answers standard ACP permission
  requests with `allow_once` when offered, otherwise cancellation. This is
  automated approval inside the disposable container, not a human review gate.
- Native auto-update, usage telemetry and automatic conversation-title
  generation are disabled through supported settings/environment options.
  Title generation is ancillary and asynchronous; disabling it avoids a
  detached title request outliving the single-prompt Case. Other native
  auxiliary model calls are not suppressed.
- No external MCP servers or tool-service egress are provisioned. Native web,
  browser, media, package-install and account-dependent tools may therefore
  be unavailable/fail. Their existence is not claimed as a deployed capability.
- Model interception uses bearer auth and Chat Completions routes. The launcher
  preserves ABB's CA/proxy variables, including `NODE_EXTRA_CA_CERTS`; it does
  not set `NODE_TLS_REJECT_UNAUTHORIZED=0` or bypass the interceptor.
- Standard ACP messages/tool events, model traffic and workspace file changes
  are the expected evidence. An outer native-record reader links committed
  main-turn model responses by explicit IDs, including plain-text final answers.
  Complete internal reasoning/subagent reconstruction is not claimed.
- A fresh native profile is intentional. Do not assume cross-Case memory,
  resume support, arbitrary user-question extensions or rich Qwen-specific ACP
  extensions. Start with one Case and one dialogue step.

## Native model-response evidence

`bootstrap/native_evidence.py` reads the pinned version's existing
`projects/*/chats/<session-id>.jsonl` inside the launcher's private `QWEN_HOME`.
It does not modify Qwen, enable outgoing telemetry, change model requests or
export native chat text. Qwen's `ui_telemetry` chat records are written even when
usage statistics and SDK telemetry are disabled.

For a normal completed prompt, Qwen flushes its records, strictly appends a
`branch_checkpoint`, and returns its UUID and assistant-record UUID in ACP
`_meta["qwen.branchPoint"]`. The reader selects exactly that checkpoint's parent
chain, bounded by `startExclusiveRecordUuid`. It exports main-turn
`qwen-code.api_response` IDs. ABB's existing native linker matches each ID to the
captured provider response ID within the Case, attaching it to the originating
Input even when the response contains no tool call.

No timestamp, text, latest-file or request-order matching is used. Missing
checkpoints, broken/truncated records, ambiguous transcripts and duplicate IDs
fail closed: a failed evidence status is recorded, without replacing the Agent
answer. Missing provider IDs, failed attempts, auxiliary/subagent work and
responses without a committed checkpoint remain unlinked by this reader; their
wire evidence can still remain at Case scope. Duplicate wire matches remain
ambiguous. Files are restricted to the profile tree, reject links, and have
bounded size, line and record counts.

This is a version-specific source contract, not a claim of a complete trace.
Recheck it when upgrading Qwen, and confirm real ACP metadata, transcript writes
and intercepted response IDs during acceptance.

## When you decide to run it

These commands are instructions for a future run; they were **not executed**.
First complete the host setup in [the onboarding guide](../../../docs/How%20To%20Add%20Agent.md),
verify the bundled source snapshot and configure the Qwen variables. Use Linux
containers. Linux/WSL is the conservative host path: the existing shared
`ACPConfig` uses host `Path.is_absolute()` for a POSIX container cwd, so its
static validation is not Windows-native portable. This unit does not alter
that shared framework behavior.

Start with the provided native JSON **string**, not a `{"prompt": ...}` object:

```bash
python -m agentbench observe qwen-code --input resources/agents/18-qwen-code/examples/local-task.json
```

That command builds and runs real Qwen and consumes model tokens. It does not
run a Judge. Then, if desired, use the local evaluation SDK:

```bash
python -m agentbench evaluate qwen-code --cases 1 --max-steps 1 --sdk local --no-view
```

Before KUMA certification, install its pinned official SDK per the guide,
validate `requirement.md`, fetch the current onboarding strategy catalog,
choose and validate a coding strategy, and add that selection to the profile.
No catalog ID was guessed or copied from another Agent here. Configure KUMA
separately and then use:

```bash
python -m agentbench certify qwen-code --sdk kuma --no-view
```

Do not manually promote the registry to `ready` in place of acceptance.

## Pending acceptance checklist

1. Confirm the pinned source snapshot, successful frozen build, complete packed assets,
   native CLI launch and compatible ACP protocol negotiation.
2. Check missing/invalid key and model errors, endpoint/region mismatch, TLS
   trust, model-route observation, rate limits and streaming/tool-call support.
3. Confirm no interactive first-run/OAuth/trust prompt; run a real local
   read/write/shell task and verify its output, permission and file evidence.
4. Inspect stdout for ACP-only traffic and stderr for sanitized errors; verify
   cancellation, timeout, failed tool status and child-process cleanup.
5. Check resource usage: the upstream build permits a 4 GiB Node heap, while
   ABB's current runtime policy is 1 CPU, 1 GiB RAM and 128 processes. Build
   resources and Case resources are different. OOM/heavy task suitability is
   unverified; do not assume changing the 900-second timeout solves it.
6. Validate the profile with the official SDK and review actual evidence and
   Judge output before certification. A successful handshake alone is not
   end-to-end acceptance.

During implementation, 25 offline synthetic checks passed for plain-text
response linkage, checkpoint isolation, streamed IDs, missing/ambiguous evidence
and compatibility with legacy readers. The temporary test files are not included
in this contribution. These checks are not substitutes for the acceptance items
above; the full ACP integration suite was not run.

## Source contracts inspected

All links below refer to the pinned source bundled in `agent/`:

- [Native packaging](agent/Dockerfile), [workspace build](agent/scripts/build.js),
  [package metadata](agent/package.json), [native entry](agent/scripts/cli-entry.js).
- [ACP implementation](agent/packages/cli/src/acp-integration/acpAgent.ts),
  [CLI configuration](agent/packages/cli/src/config/config.ts).
- [Model-provider settings](agent/docs/users/configuration/model-providers.md),
  [auth validation](agent/packages/cli/src/config/auth.ts),
  [folder trust](agent/packages/cli/src/config/trustedFolders.ts).
- [DashScope provider](agent/packages/core/src/core/openaiContentGenerator/provider/dashscope.ts),
  [wire requests](agent/packages/core/src/core/openaiContentGenerator/pipeline.ts).
- [ACP completion checkpoints](agent/packages/cli/src/acp-integration/session/Session.ts),
  [durable native chat records](agent/packages/core/src/services/chatRecordingService.ts),
  [local API-response events](agent/packages/core/src/telemetry/loggers.ts),
  [provider response IDs](agent/packages/core/src/core/openaiContentGenerator/converter.ts).
