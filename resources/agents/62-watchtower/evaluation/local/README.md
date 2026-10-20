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
  --sdk local --sdk-options resources/agents/62-watchtower/evaluation/local/sdk-options.json \
  --cases 3 --max-steps 1 --timeout 360 --case-retries 0 --no-view -y
```

The temporary registry is a copy of `resources/registry.toml` with only
Watchtower enabled. Its status remains `adapting`; acceptance is not inferred
from a completed execution. The source and outer integration must already be
present. The existing local integration is maintained separately from these
Case fixtures.

To build the viewer: `cd web && npm ci && npm run build`. Open the saved Suite
with `python -m agentbench view RESULTS_PATH --host 127.0.0.1 --port 8766`.
