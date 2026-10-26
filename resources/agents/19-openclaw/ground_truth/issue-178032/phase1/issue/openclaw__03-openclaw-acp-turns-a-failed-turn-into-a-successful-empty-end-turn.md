---
agent: openclaw
product: openclaw
repo: openclaw/openclaw
num: 3
title: [Bug]: `openclaw acp` turns a failed turn into a successful, empty `end_turn`; the Gateway's error text (e.g. "The model reached its output token limit…") never reaches the ACP client
kind: issue
ref: #178032
url: https://github.com/openclaw/openclaw/issues/178032
filed: 2026-10-20
state: closed
status: 已关闭 · 已修
replies_human: 0
replies_bot: 1
prs: https://github.com/openclaw/openclaw/pull/178057, https://github.com/openclaw/openclaw/pull/178267
gist: 
evidence_runs: 5363a2ec16cf4a579e29b35897a6c05d de607c9cda6249b8ac0eba4d8e3c8c9f
evidence_zip: 
next: 在新版本上复测，确认不再复现
note: p318 提交（复核 review_loop_20261020T034301Z 新 A；本地 mock 复现 2026.9.5 / 2026.10.5，草稿与留档 temp/upstream_filing_p318/openclaw/）；2026-10-20 07:18Z 维护者 steipete 以 completed 关闭，修复 PR #178057（fix: show failed and truncated turns in ACP clients）已合并，标 P1；ABB pin 2026.9.5 仍未含修复
checked: 20261025T040529Z
mentioned_in: https://github.com/openclaw/openclaw/pull/178154
---

# [Bug]: `openclaw acp` turns a failed turn into a successful, empty `end_turn`; the Gateway's error text (e.g. "The model reached its output token limit…") never reaches the ACP client

> We're **DefuzeX**, and we build behavioral safety testing for AI agents. We found this issue with [KUMA](https://github.com/DefuzeX-AI/KUMA-DefuzeX), our open-source SDK that checks what an agent actually does. A full reproduction is below.

### Bug type

Behavior bug (incorrect output/state without crash)

### Beta release blocker

No

### Summary

When a turn fails (for example, a reasoning model uses its whole output budget and returns `finish_reason: "length"` with empty content), the Gateway detects it and creates a user-facing error. The `openclaw acp` bridge then resolves `session/prompt` with `stopReason: "end_turn"` and sends no `agent_message_chunk`. The ACP client sees an empty turn that looks like it succeeded.

## Description

The agent runtime handles this case correctly. The ACP bridge drops the result.

1. `packages/ai/src/providers/openai-stop-reason.ts:20-21` maps `finish_reason: "length"` to `stopReason: "length"`.
2. `isIncompleteTerminalAssistantTurn` classifies a length stop with no visible text as an incomplete turn. `resolveIncompleteTurnPayloadText` produces `⚠️ The model reached its output token limit before generating an answer. Please try again.` (`incomplete-turn-resolution.ts:200-203` on main). The Gateway logs `incomplete turn detected: … stopReason=length … — surfacing error to user` and `outcome=error`. The session transcript gets a `run-failed-before-reply` entry with `display: true`.
3. `chat-send-agent-dispatch.ts` broadcasts a `chat` event with `state: "error"` and that `errorMessage`.
4. `src/acp/translator.prompt-stream.ts` `handleChatEvent` (main `a2936708`, lines 492-496; v2026.9.5, lines 527-531):
   ```ts
   if (state === "error") {
     const errorKind = payload.errorKind as string | undefined;
     const stopReason: StopReason = errorKind === "refusal" ? "refusal" : "end_turn";
     void this.finishPrompt(pending.sessionId, pending, stopReason);
   }
   ```
   `payload.errorMessage` is never read. The `aborted` branch just above it (lines 486-491) does pass its `errorMessage` to `finishPrompt` as an `interruption`, which appears as an `[OpenClaw interruption] …` chunk. The `error` branch has no equivalent.

The same thing happens for any `state: "error"` turn. We reproduced it with `finish_reason: "content_filter"` as well, so it does not depend on the model.

A related gap: the `final` branch (main lines 480-483) returns `max_tokens` only when `payload.stopReason === "max_tokens"`. OpenClaw's own runtime uses `"length"`, and nothing under `src/` produces `"max_tokens"`. A native turn that delivers a partial answer and is then cut off at the output cap therefore also ends as `end_turn` over ACP, with no truncation notice. The ACP spec has `max_tokens` for exactly this case.

Related issues:
- #44294 is about the same `state === "error"` → `end_turn` line, from the angle of preserving error kinds. This report is about the user-visible text being dropped entirely, which causes a silent empty turn, and it has a runtime reproduction.
- #108587 was the same silent-loss class on the disconnect-rejection path. It was fixed in #108827, which emits a recorded notice before settling.

## Steps to reproduce

No real model is needed. We used a local mock OpenAI-compatible server.

1. Start a mock `POST /v1/chat/completions` that streams only reasoning and then stops on length:
   ```
   data: {"choices":[{"index":0,"delta":{"role":"assistant","content":""}}], ...}
   data: {"choices":[{"index":0,"delta":{"reasoning_content":"thinking step 0 ... "}}], ...}   (x20)
   data: {"choices":[{"index":0,"delta":{},"finish_reason":"length"}], ...}
   data: {"choices":[],"usage":{"prompt_tokens":1000,"completion_tokens":8192,"completion_tokens_details":{"reasoning_tokens":8192}}}
   data: [DONE]
   ```
2. Configure a custom provider pointing at the mock: `api: "openai-completions"`, model `maxTokens: 8192` (the same value as `DEFAULT_MODEL_MAX_TOKENS` in `src/config/defaults.ts:62`). Make it `agents.defaults.model.primary`.
3. Run `openclaw gateway run`, then `openclaw acp --url ws://127.0.0.1:<port> --token-file <file>` over stdio.
4. From an ACP client, send `initialize`, `session/new`, then `session/prompt` with any text.

We can share the single-file Python script (mock server, config, and a minimal ACP client) if that helps.

## Expected behavior

The ACP client is told that the turn did not produce an answer. At minimum, the Gateway's error text should arrive as a recorded `agent_message_chunk` before the prompt settles, the way the `aborted` branch already does it. Ideally the prompt would also settle as a JSON-RPC error, which is the direction recommended in #44294. When a native turn is cut off at the output cap, the bridge should return `stopReason: "max_tokens"`.

## Actual behavior

On both 2026.9.5 and 2026.10.5, the full ACP stream for the prompt is:

```
<- session/update  session_info_update
<- session/update  usage_update
<- result          {"stopReason":"end_turn"}
```

There are no `agent_message_chunk` updates. The mock received exactly one request, so there was no retry. Meanwhile the Gateway log on 2026.10.5 shows:

```
[agent/embedded] incomplete turn detected: ... provider=abb/mock-reasoner stopReason=length ... payloads=0 tools=0 ... — surfacing error to user
[model-fallback/decision] ... reason=format next=none detail=⚠️ The model reached its output token limit before generating an answer. Please try again.
```

| mock response | ACP stopReason | text the ACP client received |
|---|---|---|
| reasoning only, `finish_reason: "length"` | `end_turn` | (nothing) |
| no content, `finish_reason: "content_filter"` | `end_turn` | (nothing) |
| partial text, then `finish_reason: "length"` | `end_turn` | the partial text only, no truncation notice |
| normal answer, `finish_reason: "stop"` (control) | `end_turn` | full answer |

We first saw this in real runs with a reasoning model (`glm-5.3-flash`, OpenAI-compatible, `max_completion_tokens: 8192`). Three separate turns hit the cap with `completion_tokens: 8192` and `reasoning_tokens: 8192`, each after 145-210 s of generation. Each one finished over ACP as `end_turn` with no output and no error. Our harness recorded them as answered turns, and the next turn's request history showed no trace of the failed one.

### OpenClaw version

2026.9.5 (ec9c1a1) and 2026.10.5 (1b58cb9), both npm. Source inspection: current main `a29367087a`.

### Operating system

Linux x86_64 (Node 26.5 on the host for the mock repro; `node:24-bookworm` container for the original runs)

### Install method

npm (`npm ci` from a pinned lockfile, `--ignore-scripts`), local Gateway + `openclaw acp` over stdio

### Model

Mock OpenAI-compatible model for the repro. The original runs used `glm-5.3-flash`.

### Provider / routing chain

Custom provider, `api: "openai-completions"` → local mock (repro) / an OpenAI-compatible endpoint (original runs)

### Impact and severity

Every ACP client (editors and headless harnesses) shows a failed turn as a successful empty reply. The user gets no hint that the model hit its output limit or that the provider refused, so they cannot react by raising `maxTokens`, retrying, or switching models. OpenClaw does record the failure in its own session transcript (a `run-failed-before-reply` entry with `display: true`), but the ACP stream never carries it.
