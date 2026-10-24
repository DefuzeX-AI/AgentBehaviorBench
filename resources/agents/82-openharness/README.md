# OpenHarness native session deployment

Source: [zhijiewong/openharness](https://github.com/zhijiewong/openharness),
commit `2a7b7b8e1c0b132241d0eebb906dc86863ca19d8` (2.47.0, MIT).
Onboarding: [#523](https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/523).
ABB restores ignored `agent/` from the pinned Git source and builds its npm lockfile.
No upstream business code is edited.

## Deployed entrypoint

The official `node dist/main.js session` command owns model requests, prompts,
tools, permissions and conversation history. An outer Python ACP transport bridge
exposes this NDJSON session to ABB. This is explicitly **not** upstream `oh acp`.
The native session's full CLI prompt and explicit `trust` permission mode apply.
No tools are removed, and no external MCP server is provisioned.

Upstream ACP drops the normalized model name and ignores custom baseUrl. Its
first real two-turn Smoke received HTTP 400 twice and Local Judge was inconclusive.
That historical run used the old entrypoint and does not validate this deployment.
The user approved switching to the official session entrypoint after offline tests.

## Model configuration

DeepSeek is selected by `[model] provider="deepseek"`. ABB supplies its standard
runtime-owned `ABB_AGENT_MODEL_*` variables; set `DEEPSEEK_MODEL=deepseek-chat`
and `DEEPSEEK_API_KEY` in the normal host configuration for a future real run.
No key belongs in the image, command line or generated configuration file.
The launcher maps the runtime credential to the native OpenAI-compatible provider
and writes only model/baseUrl to a fresh HOME. OpenAI-compatible is the wire
protocol, not a switch to the OpenAI service. Native session normalizes
`openai/deepseek-chat` to `deepseek-chat` in the actual request.
Only simple, unprefixed model IDs are supported. CA settings remain available.
Routes and credentials are bound by ABB rather than statically overridden.

## Evidence and errors

Native session real-time output omits tool arguments. The query loop also fails
to forward tool_call_complete, so persisted messages alone are insufficient.
The external `request_evidence.mjs` observer records only existing tool-call fields
from already-serialized outgoing model messages, forwarding fetch arguments and
responses unchanged. It records no headers or API keys and makes no network calls.
This is transport observation, not model rewriting or a tool implementation.

After native turn completion, the bridge correlates observed call IDs/arguments,
persisted native results and streamed tool outcomes. Missing, conflicting or
mismatched evidence fails the invocation; missing data is never fabricated.
ACP tool events are emitted after the turn and marked accordingly, so their timing
is not a measurement of native tool latency. Text remains streamed. Errors become
JSON-RPC errors and close the native session; they do not become successful empty
replies. Cancellation terminates the session. This transport currently treats any
native error event as terminal, even if upstream might subsequently recover; this
conservative integration boundary is documented and must not be counted as an
upstream behavioral defect.

One ACP session owns one native CLI process and fresh HOME/XDG directories.
Successive inputs retain its native history; different Cases do not share it.
Workspace isolation remains ABB's responsibility. No resume/MCP/media capabilities
are advertised. Closing stdin and terminating the ABB process group cleans up
native subprocesses.

## Validation status

Offline fixtures covered file tools, model normalization, session isolation,
error propagation, cancellation and missing-evidence rejection. Their fake model
service did not validate tool-result / tool-call correspondence, so they did not
establish valid cross-turn model history.

A real two-turn session Smoke completed the first turn but failed on the second:
native history retained tool results without the corresponding assistant tool
calls. Ten subsequent independent Cases with frozen source, inputs and configuration
all reproduced this malformed history (10/10; no infrastructure replacements).
Each Case started with an empty workspace and a fresh session. No upstream business
logic was changed. Local Judge returned inconclusive before making a model call.
This is a defect candidate pending manual review, not an accepted GT or a passed
Smoke. The task's onboarding-before-GT prerequisite is still outstanding.

The unit remains disabled/adapting. Do not repair or synthesize native history in
the transport merely to make Smoke pass. Maintainer guidance is needed on handling
this upstream blocker before publishing an onboarding PR. The separately retained
technical evidence is not part of the production agent unit.
