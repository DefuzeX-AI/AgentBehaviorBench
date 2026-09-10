# Interception acceptance

Run from the AgentBehaviorBench root:

```sh
python -m tests.acceptance.interception.run --list
python -m tests.acceptance.interception.run --controlled --faults
python -m tests.acceptance.interception.run --live --model openai/gpt-4.1-mini
```

The last command incurs model charges and reads .env on the host only.
Ordinary pytest does not call real models. --cases accepts comma-separated
names; --source-model google=gemini-2.5-flash changes a source identity;
--model changes the actual OpenRouter target. --output must name a fresh folder.

Folders:

- tests/fixtures/llm-probe: standalone selectable client Agent, manifest and image.
- upstream.py: controlled TLS HTTP upstream, fragmented/delayed SSE and faults.
- lab.py: root-owned proxy/upstream plus UID 10001 original client process in an
  internal Docker network; no real credentials or external model access.
- faults.py: controlled-only auth/error/gzip/concurrency/deadline/cancel checks.
- run.py: opt-in orchestration. Live mode reuses DockerRuntime/invoke_once and
  the existing worker, rather than inventing a production container runner.

The lab requires Linux netfilter support via Docker, NET_ADMIN/NET_RAW and
SETUID/SETGID for its child process. Production keeps Agent and proxy in separate
containers with the existing restricted policies; only the lab needs to launch
both roles in one namespace. Mounts are scoped; .env is never mounted in the lab.

Evidence goes to results/interception/<run-id>. Controlled runs save the
matrix, trace and proxy diagnostics; live runs save the matrix, worker result,
framework trace, network trace and invocation diagnostics. Failed attempts are
retained, not replaced by later passing results.
