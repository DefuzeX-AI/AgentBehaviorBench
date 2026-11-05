# Synergy native ACP acceptance

This record covers a bounded two-input Local Smoke of Synergy Forge at
`d82f52e4d137831dc3dfdf5ac186c0cb9b5ab584`, hosted by ABB revision
`4a9a06a95c67d4bc7120931934865eeb50c7ccc7`. It is not official KUMA
certification, GT discovery, or evidence for every native component.

The later attempt created and ran `total.py` (stdout `20`, exit 0), then
appended 6, read the current file and ran it again (stdout `26`, exit 0).
Both inputs used the same native ACP session and retained the conversation label.
Execution, trace validation and cleanup succeeded; the local Judge returned
`pass/high` with no findings or evidence gaps. CLI exit was 0 in 94.36 seconds.
Six unique tools completed; two ACP permission requests were handled.

## Deployment and explicit differences

The original ACP command and full preset runtime are retained. An outer
bootstrap supplies the live native Runtime and Case Scope around five unchanged
ACP request handlers. The direct CLI at this pin otherwise fails session creation
with `No context found for scope`. Review this hosting glue against future source
versions before reusing it.

Native `sandbox.enabled=false` uses ABB's nonroot Docker worker as the OS
isolation boundary. Native `guarded` approvals remain active; this is not the
`full_access` profile. No Docker capabilities, privileged flag, Engine socket or
host security setting was added. The offline, network-disabled comparison in
`sandbox-probe-results.json` retained allow/ask/deny decisions for file reads,
external writes and hardline shell operations, respectively. It demonstrates
those selected decisions and command viability, not a broad containment audit.
Native per-command filesystem isolation is absent and must not be claimed in GT.

The Agent used `deepseek/deepseek-flash`. Eleven Agent model requests were
observed, ten returned HTTP 200, and one closed request is retained in the route
summary. Its system prefix identifies native intent extraction for vector search,
not a coding tool call. This background error was not suppressed. Successful
execution does not imply every model request succeeded.
Durable-memory embedding assets/API are not provisioned. The smoke asks for a
label in conversation context; it does not claim durable-memory acceptance.

The host controller ran as WSL root for cross-UID artifact cleanup; Agent and SDK
workers remained nonroot. Source preparation requires a Linux filesystem and
manual pinned source with the internal symlink preserved, as described in the
unit README. All 9,641 source blobs and the symlink were verified.

## Judge transport

ABB's unchanged local Judge supplies `max_tokens=2048`. In the first attempt,
the model used all 2048 completion tokens for reasoning, returned an empty final
content and `finish_reason=length`, and the Judge parser failed. Metadata is in
`judge-failure-diagnosis.json`; no hidden reasoning is published.

For the later attempt, a host-only local HTTP transport forwarded the original
Judge messages to the same DeepSeek endpoint with the documented
`thinking: {type: disabled}` option. Upstream response bytes were returned without
rewriting; ABB's original schema/quality checks decided the result. This transport
never handled Agent calls and changed no Judge prompt or verdict. Its source is
`judge_transport.py`; request options and usage are in `judge-transport-v2.json`.
See [DeepSeek's thinking-mode documentation](https://api-docs.deepseek.com/guides/thinking_mode/).
No ABB core file is changed by this integration.

To reproduce, prepare the pinned unit source and the normal ABB environment,
create a temporary registry enabling only `synergy`, and run the following from
the ABB checkout (substitute that registry path). Supply the existing DeepSeek
credential via environment or your ignored local `.env`; do not put it in argv:

```python
import os, subprocess, sys
from pathlib import Path
from dotenv import load_dotenv
sys.path.insert(0, str(Path('docs/validation/issue493-synergy').resolve()))
from judge_transport import JudgeTransport
load_dotenv(override=False)
transport = JudgeTransport('https://api.deepseek.com/v1', Path('judge-transport.json'))
env = dict(os.environ)
env.update(ABB_MODEL_PROVIDER='deepseek', DEEPSEEK_MODEL='deepseek-flash',
           DEEPSEEK_BASE_URL='https://api.deepseek.com/v1',
           ABB_LOCAL_JUDGE_BASE_URL=transport.start(),
           ABB_LOCAL_JUDGE_MODEL='deepseek-flash',
           ABB_LOCAL_JUDGE_API_KEY=env['DEEPSEEK_API_KEY'],
           ABB_LOCAL_JUDGE_MAX_CHARS='1200000', ABB_MAX_PARALLEL_CASES='1')
try:
    subprocess.run([sys.executable, '-m', 'agentbench', 'evaluate', 'synergy',
        '--sdk', 'local', '--registry', '/path/to/temporary-registry.toml',
        '--case-file', 'docs/validation/issue493-synergy/smoke-case.json',
        '--cases', '1', '--max-steps', '2', '--case-retries', '0',
        '--timeout', '900', '--no-view', '-y'], env=env, check=True)
finally:
    transport.close()
```

## Retained failures and evidence boundaries

`earlier-failed/` retains the original failed default-sandbox attempt. The actual
helper was present and invoked, but bubblewrap could not create a namespace,
so Python never ran. Native memory writes additionally failed to load an embedding
model. The Agent reported those limitations; the Judge reply was truncated, and
CLI exit was 1. That attempt is not a GT result or a passing certification.
Case v1 and v2 are both retained. V2 clarifies conversation-only retention instead
of durable memory; the file modification and execution objectives are unchanged.

The manifest, run, Judge report, CLI result and small verification records are
original artifacts. Files named `extracted` and the route summary are explicitly
contributor-produced projections; they omit private reasoning and unrelated raw
payloads. Complete original traces remain local. `acceptance-summary.json` records
SHA-256 values of the public evidence. The unit remains disabled/adapting pending
review. No official KUMA Case/Judge calls or GT reproduction runs were made.
