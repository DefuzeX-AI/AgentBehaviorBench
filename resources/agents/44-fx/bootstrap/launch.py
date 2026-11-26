"""Map ABB's selected OpenAI-compatible model onto fx's native ACP server."""
from __future__ import annotations

import json
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
FX_BIN = "/opt/fx/bin/fx"
CONNECTION = "abb"
CONNECTION_KEY_ENV = "FX_ABB_API_KEY"


def settings_for(relay_url: str, model: str) -> dict:
    """fx user settings: one `openai-chat-completions` connection, selected.

    The connection reads its bearer key from CONNECTION_KEY_ENV at request
    time, so the file holds no secret.
    """
    return {
        "provider": CONNECTION,
        "models": {CONNECTION: model},
        "providers": {
            CONNECTION: {
                "protocol": "openai-chat-completions",
                "base_url": f"{relay_url}/v1",
                "auth": {"type": "bearer", "env": CONNECTION_KEY_ENV},
            }
        },
    }


def prepare(environ: dict[str, str], home: Path, start_relay=model_relay.start) -> tuple[list[str], dict[str, str]]:
    """Write fx settings under `home` and return the ACP command and child environment.

    fx's HTTP client does not use HTTPS_PROXY, so its connection points at the
    loopback model relay (see model_relay.py), which must not go through the
    runtime proxy either.
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
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")

    _, url = start_relay(base_url)
    settings_dir = home / ".fx"
    settings_dir.mkdir(parents=True, exist_ok=True)
    (settings_dir / "settings.json").write_text(json.dumps(settings_for(url, model), indent=2) + "\n")

    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = {k: v for k, v in environ.items() if k != KEY_ENV}
    child.update({"HOME": str(home), CONNECTION_KEY_ENV: key, "FX_AUTO_UPGRADE": "0",
                  "FX_DISABLE_KEYCHAIN": "1", "NO_PROXY": no_proxy, "no_proxy": no_proxy})
    return [FX_BIN, "acp"], child


def main() -> int:
    try:
        # Disposable HOME: ~/.fx settings, sessions and logs stay per Case and
        # writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-fx-home-"))
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
    # fx runs as a child so the relay thread stays alive; it inherits the ACP
    # stdio directly.
    child = subprocess.Popen(command, env=environ)
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
