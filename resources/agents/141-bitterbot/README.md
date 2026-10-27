# Bitterbot native ACP integration

Issue: https://github.com/DefuzeX-AI/AgentBehaviorBench/issues/463

## Source and execution

The source is pinned to Bitterbot `1.10.1` commit
`733b741952b627b1ca34aa892a8d1b4a9333e7b6` (MIT). ABB's normal Git source
preparation restores all 5,814 tracked files into ignored `agent/`; source,
tools, prompts and native approval logic are unchanged. Docker installs from the
original pnpm workspace lock and runs the full original `pnpm build`.

`bootstrap/launch.py` starts the original `bitterbot.mjs gateway run`, waits for
its native listening announcement and starts `bitterbot.mjs acp` on stdio.
Gateway output is kept out of the ACP stream. Incoming ACP bytes are held until
the native bridge reports its completed Gateway handshake (`onHelloOk`), then
forwarded without parsing or rewriting. This avoids sending the first prompt
before native WebSocket authentication completes. Both processes are stopped on
shutdown. The private HOME/state directory and random Gateway token isolate one
Case. The original CLI no-respawn option avoids an extra warning-filter process.
Credentials are read from runtime-owned `ABB_AGENT_MODEL_*` settings and
referenced by environment substitution in the native JSON config, never in argv.
The model is an ordinary custom OpenAI-compatible provider; no provider pin or
fallback is added.

The workspace, preconfigured bootstrap option, model, loopback Gateway, managed
headless Chromium and optional background-service settings use native config.
P2P, Circles, dreaming, cron and interval heartbeats are disabled for one-shot
Cases. No tool profile or approval policy is overridden. Browser setup does not
prove a browser task passed; see the Profile and validation record for limitations.

The exact Gateway and local CDP routes are in `network/rules.toml`. Model traffic
uses the shared runtime interception route. External tool access is not supplied.

## Native compilation cache

Cold native plugin-SDK transpilation exceeded Node's default heap under ABB's
normal 1 GiB container budget. The Docker build warms the original Gateway's
Jiti cache once, offline, with a disposable configuration and no Case or model
request. It retains only compiled original-source cache files in the writable,
disk-backed `TMPDIR`; private warmup state is deleted. No native tool, prompt,
approval or source file is changed. Normal Cases keep the default Node heap; only the build-time compiler gets a
larger heap. The unit declares a 2 GiB Agent memory limit: the unmodified native
first prompt with local embeddings exceeded 1 GiB (kernel OOM), while the same
configuration at 2 GiB stayed alive with a measured 1,525,190,656-byte peak.
Other Agents and SDK controllers retain the default 1 GiB limit.
This requires the shared runtime support in
https://github.com/DefuzeX-AI/AgentBehaviorBench/pull/658; current main does not
apply the declared limit and the first prompt has been observed to OOM.

## Native local embedding asset

`src/memory/embeddings.ts` declares the default EmbeddingGemma GGUF. Its exact
identifier, immutable Hugging Face revision, byte length and LFS SHA256 are in
`embedding-model.json`. The Docker build downloads and verifies that original
328,577,056-byte model. Native `memorySearch.local.modelPath` selects the same
weights from `/opt/agent/models`; no remote embedding service or runtime model
download is needed, and the native memory implementation/tools are preserved.
Weights are image build material and are not committed to this repository.

## Checks and acceptance

```bash
python -m pytest -q tests/test_issue463.py tests/test_agent_manifest*.py
python - <<'PY'
from pathlib import Path
from agentbench.onboarding.build_agent_env.common.validation import validate_unit
from agentbench.sdk.plugin.kuma.plugin import plugin
print(validate_unit(Path("resources/agents/141-bitterbot"), plugin))
PY
```

A fresh source-preparation check must copy only the outer unit into an empty
location, run `prepare_agent_source()` there and load/validate its configuration.
The current Profile uses `basic-safety-coding@1`, selected and checked against the
live KUMA catalog; static validation alone does not establish runtime acceptance.

Enable this unit in a temporary registry for explicit evaluation, keeping the
committed registration disabled/adapting until acceptance is reviewed.

The launcher supplies the native ACP `--session` option with a unique canonical
`agent:main:abb-<random>` key. This preserves native event routing and keeps
separate Case sessions isolated without rewriting protocol messages.
