"""Launch Autohand's native ACP server with ABB's selected model profile."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

BINARY = "/opt/agent/agent/node_modules/.bin/autohand"
WORKSPACE = "/home/agent/workspace"
PROVIDERS = {"openrouter": "openrouter", "deepseek": "deepseek", "glm": "zai"}


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    for name in ("ABB_AGENT_MODEL_PROVIDER", "ABB_AGENT_MODEL_API_KEY",
                 "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"):
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    provider = PROVIDERS.get(environ["ABB_AGENT_MODEL_PROVIDER"])
    if provider is None:
        raise ValueError("Unsupported ABB model provider")
    base = environ["ABB_AGENT_MODEL_BASE_URL"].rstrip("/")
    url = urlsplit(base)
    if (url.scheme != "https" or not url.hostname or url.username or url.password
            or url.query or url.fragment):
        raise ValueError("ABB_AGENT_MODEL_BASE_URL must be an HTTPS URL without credentials, query or fragment")

    native_home = home / ".autohand"
    native_home.mkdir(mode=0o700, parents=True)
    config = native_home / "config.json"
    document = {
        "provider": provider,
        provider: {"apiKey": environ["ABB_AGENT_MODEL_API_KEY"], "baseUrl": base,
                   "model": environ["ABB_AGENT_MODEL"]},
        "permissions": {"mode": "interactive"},
        "telemetry": {"enabled": False, "enableSessionSync": False},
        "traces": {"enabled": False, "cloudSync": False},
        "autoReport": {"enabled": False},
    }
    with open(config, "x", encoding="utf-8", opener=lambda path, flags: os.open(path, flags, 0o600)) as output:
        json.dump(document, output)
    child = {
        **environ,
        "HOME": str(home), "AUTOHAND_HOME": str(native_home), "AUTOHAND_CONFIG": str(config),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "AUTOHAND_SKIP_PING": "1",
        "AUTOHAND_SKIP_UPDATE_CHECK": "1",
    }
    return [BINARY, "--acp", "--config", str(config)], child


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-autohand-"))
        command, child = prepare(dict(os.environ), home)
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get("ABB_AGENT_MODEL_API_KEY") or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
