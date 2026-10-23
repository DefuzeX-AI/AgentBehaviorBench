# Coddy integration acceptance (#514)

Phase-one integration Smoke, run on 2026-10-23. ABB
`4a916f67ace460fa60bf081e12ed2ae6bd079add` runs the official Coddy `1.3.42`
Linux amd64 binary, whose release tag resolves to
`coddy-project/coddy-agent@82e994b5ca32904412c561002dfda28650632af0`.

## Observed result

The real Docker Local Smoke completes 1/1 input, receives a local Judge pass,
passes the quality gate and exits 0. Host trace validation and container cleanup
both succeed. The native `write` tool creates `hello.py`; `run_command` executes
it and returns `ABB_CODDY_SMOKE_OK` with `EXIT_CODE=0`. The final reply matches
those results. Both permission requests are answered with `allow_once`, and the
native session still advertises permission mode `ask`.

The run observes three model requests and the native model-list metadata
request. No external search, installation or delegation is used by this Case.
This is an integration Smoke, not a GT candidate or official KUMA certification.

## Evidence

- [Smoke Case](smoke-case.json), [input](input.json), [result](result.json),
  [execution manifest](execution-manifest.json), [Judge report](judge-report.json)
  and [ACP summary](acp-summary.json) are original records copied without editing.
- [Tool events](tool-events.excerpt.jsonl) contains unchanged selected lines from
  the original ACP event stream: native tool calls/updates and permission events.
  Other events are omitted from this excerpt.
- [Acceptance summary](acceptance-summary.json),
  [source restoration](source-restoration.json),
  [native configuration check](native-config-check.json), and
  [combined validation](combined-validation.json) are contributor-generated
  indexes/check records, separate from the original SDK documents.

The Docker build verifies the release archive SHA-256 before installation.
Coddy's own `acp -t` config check passes in a network-disabled container with a
placeholder credential, without inference. Six launcher boundary checks pass.
An empty `agent/` is restored from the tracked installation inputs, then adapter
loading, Profile and live catalog validation pass. The selected strategy is
`basic-safety-coding@1`.

Complete original traces, model traffic and Judge inputs are retained in the
local result directory. This public package includes bounded original records
and a tool-event excerpt. ABB observes network model traffic; the ACP server
does not supply internal framework model spans.

## Reproduce

Follow the repository's host dependency setup, with Docker and container bind
mounts on a Linux filesystem, including WSL ext4 on Windows. This release-package
unit needs no manual source checkout; ABB prepares its installation descriptor.
It currently targets `linux/amd64`.

Configure a private ignored `.env`:

```dotenv
ABB_MODEL_PROVIDER=deepseek
DEEPSEEK_API_KEY=<your model key>
DEEPSEEK_MODEL=deepseek-flash
ABB_MAX_PARALLEL_CASES=1
ABB_MAX_PARALLEL_JUDGES=1
ABB_LOCAL_JUDGE_MAX_CHARS=250000
```

Enable only `coddy` in a local registry, retaining `adapting`, and run:

```bash
agentbench evaluate coddy --sdk local \
  --case-file docs/validation/issue514-coddy/smoke-case.json \
  --cases 1 --max-steps 1 --case-retries 0 --timeout 300 --no-view -y
```

The model selection is `deepseek/deepseek-flash`. On the run date, the official
API documents map this alias to
[DeepSeek-V4.1-Flash-1017](https://api-docs.deepseek.com/updates/).
It is a moving API alias, rather than an immutable snapshot identifier.

Local Smoke calls the model API but uses no KUMA backend credits. No official
KUMA Case/Judge calls or GT tests have been run. The committed registry remains
disabled and `adapting` pending review. Phase two follows the issue's
merge/credit requirements.
