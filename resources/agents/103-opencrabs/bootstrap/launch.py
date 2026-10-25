"""Map ABB's selected OpenAI-compatible model onto OpenCrabs' native ACP server."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import model_relay


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
OPENCRABS_BIN = "/opt/opencrabs/bin/opencrabs"
PROVIDER = "abb"
# OpenCrabs reads a custom provider's key only from keys.toml; the relay replaces
# this placeholder with the selected key.
PLACEHOLDER_KEY = "abb-model-relay"
FALLBACK_SUGGESTED_MARKER = ".fallback-chain-suggested"


def config_toml(relay_url: str, model: str) -> str:
    """OpenCrabs config: one enabled custom provider on the relay, built-in provider off,
    no startup self-update. Everything else keeps upstream defaults."""
    return (
        "[providers.opencrabs]\n"
        "enabled = false\n"
        "\n"
        f"[providers.custom.{PROVIDER}]\n"
        "enabled = true\n"
        f'base_url = "{relay_url}/v1/chat/completions"\n'
        f'default_model = "{model}"\n'
        f'models = ["{model}"]\n'
        "\n"
        "[agent]\n"
        f'default_provider = "{PROVIDER}"\n'
        f'default_model = "{model}"\n'
        "auto_update = false\n"
    )


def keys_toml() -> str:
    return f'[providers.custom.{PROVIDER}]\napi_key = "{PLACEHOLDER_KEY}"\n'


def prepare(environ: dict[str, str], home: Path, start_relay=model_relay.start) -> tuple[list[str], dict[str, str]]:
    """Write ~/.opencrabs/{config,keys}.toml under `home` and return the ACP command and environment."""
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    if not base_url:
        raise ValueError(f"{BASE_URL_ENV} is required")
    if not model:
        raise ValueError(f"{MODEL_ENV} is required")
    if '"' in model or "\\" in model or "\n" in model:
        raise ValueError(f"{MODEL_ENV} contains characters that cannot be written to config.toml")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")

    _, url = start_relay(base_url, key)
    config_dir = home / ".opencrabs"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(config_toml(url, model))
    keys = config_dir / "keys.toml"
    keys.write_text(keys_toml())
    keys.chmod(0o600)
    # OpenCrabs prepends a one-shot "set up a fallback chain" system note to the
    # first user turn of a fresh install and records it with this marker
    # (brain/agent/service/fallback_suggest.rs). Every Case is a fresh HOME, so
    # without the marker every Case would carry that note.
    (config_dir / FALLBACK_SUGGESTED_MARKER).write_text("suggested\n")

    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = {k: v for k, v in environ.items() if k != KEY_ENV}
    child.update({"HOME": str(home), "NO_PROXY": no_proxy, "no_proxy": no_proxy})
    return [OPENCRABS_BIN, "acp", "--model", model], child


def main() -> int:
    try:
        # Disposable HOME: ~/.opencrabs config, sessions, memory and brain files
        # stay per Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-opencrabs-home-"))
        command, environ = prepare(dict(os.environ), home)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    # ABB prepares the Case workspace as a world-writable host directory and
    # removes it from the host after the run; directories the agent creates
    # (e.g. Python's __pycache__) would otherwise be 0755 and owned by the
    # container uid, which the host cannot delete. Keep them as permissive as
    # the prepared workspace.
    os.umask(0)
    # OpenCrabs runs as a child so the relay thread stays alive; it inherits the
    # ACP stdio directly.
    child = subprocess.Popen(command, env=environ)
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
