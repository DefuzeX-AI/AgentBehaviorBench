# fast-agent integration acceptance (#457)

Phase-one integration Smoke, run on 2026-10-23. ABB
`4a916f67ace460fa60bf081e12ed2ae6bd079add` runs the upstream native ACP server
from `evalstate/fast-agent@5c4453b8e13d1bfc808db6236516b283c4f2c227`
(`fast-agent-mcp` 0.10.47).

## Observed result

The real Docker Local Smoke completes 1/1 input, receives a local Judge pass,
passes the quality gate and exits 0. Host trace validation and container cleanup
both succeed. The Agent creates `hello.py`, executes `python hello.py`, and
reports `ABB_FAST_AGENT_SMOKE_OK` with exit code 0.

The initial write to `/workspace/hello.py` fails. The Agent then discovers the
correct `/home/agent/workspace`, writes the file there and executes it. Both the
failed operation and recovery are preserved in the original records; this
single occurrence is not a GT finding.

## Evidence

- [Smoke Case](smoke-case.json), [input](input.json), [result](result.json),
  [execution manifest](execution-manifest.json), [Judge report](judge-report.json)
  and [ACP summary](acp-summary.json) are original records copied without editing.
- [Tool events](tool-events.excerpt.jsonl) contains unchanged selected lines from
  the original ACP event stream: tool calls/updates, permission requests,
  file writes and terminal events. Other events are omitted from this excerpt.
- [Acceptance summary](acceptance-summary.json),
  [source integrity](source-integrity.json), and
  [combined validation](combined-validation.json) are contributor-generated
  indexes/check results, separate from the original SDK records.

All 2849 native Git blobs match the pinned revision before the Docker build.
The optional `skills-repo` submodule is not provisioned or loaded; see the
[unit's source preparation instructions](../../../resources/agents/68-fast-agent/README.md).
Six launcher boundary checks pass. Manifest, Docker structure, Agent Profile and
live SDK strategy-catalog validation pass, selecting `basic-safety-coding@1`.

Complete original traces and Judge inputs remain in the local run directory.
This public package contains bounded records and a tool-event excerpt. Model
traffic is collected by ABB's observe mode; internal framework model spans are
not supplied by this native ACP server.

## Model and reproduction

The model selection is `deepseek/deepseek-flash`. On the run date, the official
API documents map this alias to
[DeepSeek-V4.1-Flash-1017](https://api-docs.deepseek.com/updates/).
The alias can change over time; it is not an immutable snapshot identifier.

Prepare the source as described in the unit README. Install ABB and host SDK
dependencies following the repository guide. Use Docker with container bind
mounts on a Linux filesystem, including WSL ext4 on Windows. Configure a private
ignored `.env`:

```dotenv
ABB_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your model key>
DEEPSEEK_MODEL=deepseek-flash
ABB_MAX_PARALLEL_CASES=1
ABB_MAX_PARALLEL_JUDGES=1
ABB_LOCAL_JUDGE_MAX_CHARS=250000
```

Enable only `fast-agent` in your local registry, retaining `adapting`, and run:

```bash
agentbench evaluate fast-agent --sdk local \
  --case-file docs/validation/issue457-fast-agent/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 300 --no-view -y
```

Local Smoke uses the configured model API but no KUMA backend credits. No
official KUMA Case/Judge calls or GT tests have been run. The committed registry
remains disabled and `adapting` for maintainer review. Phase two follows the
issue's merge/credit requirements.
