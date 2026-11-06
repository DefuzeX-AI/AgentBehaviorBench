# Watchtower local acceptance cases

These custom KUMA Case artifacts replace the local SDK's generic conversation
prompts for this scan-oriented Agent. They retain the local SDK's real model
Judge, trace capture, container execution and model interception.

The cases cover missing input, an invalid URL, and scanning `127.0.0.1` inside
the isolated Agent container. No external scan target is supplied. A passing
loopback case does not establish accuracy against a real vulnerable application,
all tool availability, or official DefuzeX cloud certification.

Run from the repository root with the existing model credentials in `.env`:

```sh
python - <<'PYTHON'
from pathlib import Path
source = Path("resources/registry.toml").read_text()
marker = '[[agents]]\nagent_id = "watchtower"'
start = source.index(marker)
source = source[:start] + source[start:].replace("enabled = false", "enabled = true", 1)
Path("cache").mkdir(exist_ok=True)
Path("cache/watchtower-test-registry.toml").write_text(source)
PYTHON
python -m agentbench evaluate watchtower --registry cache/watchtower-test-registry.toml \
  --sdk local --sdk-options resources/agents/143-watchtower/evaluation/local/sdk-options.json \
  --cases 3 --max-steps 1 --timeout 360 --case-retries 0 --no-view -y
```

The temporary registry is a copy of `resources/registry.toml` with only
Watchtower enabled. Its status remains `adapting`; acceptance is not inferred
from a completed execution. The source and outer integration must already be
present. The existing local integration is maintained separately from these
Case fixtures.

## Loopback HTTP fixture scan

The container loopback normally has no web service, so a scan there cannot
observe an application. `fixture/` holds a one-page static site. With
`WATCHTOWER_LOOPBACK_FIXTURE=1` exported on the host, the image entrypoint
serves it with `python -m http.server` on `127.0.0.1:8000` inside the Agent
container; unset, the entrypoint only runs the launch command. The fixture is
for local acceptance only and is not part of official Case generation.

`WATCHTOWER_TOOLS` is the headless form of the native tool-selection menu
(comma-separated names; unset means all tools). The fixture run uses
`whatweb,wafw00f`; see `../2026-11-07-loopback-fixture-scan.md` for why the
recon triggers and `nmap` are left out of this bounded run.

```sh
WATCHTOWER_LOOPBACK_FIXTURE=1 WATCHTOWER_TOOLS=whatweb,wafw00f \
ABB_MODEL_PROVIDER=deepseek ABB_MODEL=deepseek-chat \
python -m agentbench evaluate watchtower --registry cache/watchtower-test-registry.toml \
  --sdk local --case-file resources/agents/143-watchtower/evaluation/local/fixture-cases.json \
  --cases 1 --max-steps 1 --timeout 360 --case-retries 0 --no-view -y
```

To build the viewer: `cd web && npm ci && npm run build`. Open the saved Suite
with `python -m agentbench view RESULTS_PATH --host 127.0.0.1 --port 8766`.

The earlier 2026-10-20 results used `ABB_CHAT_THINKING=disabled`, which is not
part of main; that shared switch is proposed separately in #561. On current
main, choose a model whose default latency fits the bounded scan budget. The
Judge and native Agent source are unchanged.
