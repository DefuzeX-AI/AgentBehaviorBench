"""Map ABB's selected OpenAI-compatible model onto Stakpak's native ACP server."""
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
STAKPAK_BIN = "/opt/stakpak/bin/stakpak"
# Stakpak only registers its OpenAI provider when OPENAI_API_KEY is set; the relay
# replaces this placeholder with the selected key.
PLACEHOLDER_KEY = "abb-model-relay"


def config_toml(relay_url: str, model: str) -> str:
    """Stakpak config: local mode, the built-in OpenAI provider on the relay, telemetry off.

    Over ACP Stakpak resolves only anthropic/, openai/ and google/ models
    (src/commands/acp/server.rs), so a custom provider cannot be selected there.
    """
    return (
        "[profiles.default]\n"
        'provider = "local"\n'
        f'model = "openai/{model}"\n'
        "\n"
        "[profiles.default.providers.openai]\n"
        'type = "openai"\n'
        f'api_endpoint = "{relay_url}/v1"\n'
        "\n"
        "[settings]\n"
        "collect_telemetry = false\n"
    )


def prepare(environ: dict[str, str], home: Path, start_relay=model_relay.start) -> tuple[list[str], dict[str, str]]:
    """Write ~/.stakpak/config.toml under `home` and return the ACP command and environment.

    Stakpak runs in local mode (no Stakpak API key). Its model calls go to the
    loopback relay (see model_relay.py), which holds the real key and must not go
    through the runtime proxy.
    """
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
    config_dir = home / ".stakpak"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "config.toml").write_text(config_toml(url, model))

    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = {k: v for k, v in environ.items() if k != KEY_ENV}
    child.update({"HOME": str(home), "OPENAI_API_KEY": PLACEHOLDER_KEY,
                  "NO_PROXY": no_proxy, "no_proxy": no_proxy})
    return [STAKPAK_BIN, "acp"], child


def main() -> int:
    try:
        # Disposable HOME: ~/.stakpak config, sessions and local database stay
        # per Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-stakpak-home-"))
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
    # Stakpak runs as a child so the relay thread stays alive; it inherits the
    # ACP stdio directly.
    child = subprocess.Popen(command, env=environ)
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
