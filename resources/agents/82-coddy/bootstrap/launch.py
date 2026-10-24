"""Run Coddy's native ACP server using ABB's selected model and credential."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
BINARY = "/opt/coddy/coddy"
WORKSPACE = "/home/agent/workspace"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict]:
    for name in (KEY_ENV, BASE_ENV, MODEL_ENV):
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    base = environ[BASE_ENV].rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError(f"{BASE_ENV} must be an HTTPS URL without credentials, query or fragment")
    model = "abb/" + environ[MODEL_ENV]
    settings = {
        "providers": [{"name": "abb", "type": "openai", "api_base": base}],
        "models": [{"model": model}],
        "agent": {"model": model},
    }
    # Coddy's provider convention reads ABB_API_KEY when api_key is omitted.
    # The native YAML and any native config-save operation therefore contain no key.
    child = {**environ, "ABB_API_KEY": environ[KEY_ENV], "HOME": str(home),
             "CODDY_HOME": str(home / ".coddy"),
             "XDG_CONFIG_HOME": str(home / ".config"),
             "XDG_DATA_HOME": str(home / ".local/share"),
             "XDG_STATE_HOME": str(home / ".local/state"),
             "XDG_CACHE_HOME": str(home / ".cache")}
    command = [BINARY, "acp", "--config", str(home / "config.yaml"),
               "--home", child["CODDY_HOME"], "--cwd", WORKSPACE]
    return command, child, settings


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-coddy-"))
        command, child, settings = prepare(dict(os.environ), home)
        # JSON is valid YAML; a serializer preserves model IDs and URL strings.
        (home / "config.yaml").write_text(json.dumps(settings, indent=2), encoding="utf-8")
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
