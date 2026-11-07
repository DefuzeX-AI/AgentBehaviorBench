"""Start Blade's native ACP server with one runtime-selected model channel."""
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
BINARY = "/opt/agent/agent/node_modules/.bin/blade"
BRIDGE = "/opt/agent/bootstrap/acp-compat.mjs"
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
    config = {
        "currentModelId": "abb-model",
        "modelProviders": {"abb": {
            "name": "ABB selected model",
            "baseUrl": base,
            "wireApi": "openai-completions",
            "apiKeyEnv": KEY_ENV,
        }},
        "models": [{"id": "abb-model", "provider": "abb", "model": environ[MODEL_ENV]}],
    }
    child = {**environ, "HOME": str(home),
             "BLADE_STORAGE_ROOT": str(home / ".blade"),
             "XDG_CONFIG_HOME": str(home / ".config"),
             "XDG_DATA_HOME": str(home / ".local/share"),
             "XDG_STATE_HOME": str(home / ".local/state"),
             "XDG_CACHE_HOME": str(home / ".cache")}
    return ["node", BRIDGE, BINARY, "--acp"], child, config


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-blade-code-"))
        command, child, config = prepare(dict(os.environ), home)
        native_root = home / ".blade"
        native_root.mkdir(mode=0o700)
        # Native apiKeyEnv stores only the variable name, never its credential.
        (native_root / "config.json").write_text(json.dumps(config, indent=2), encoding="utf-8")
        os.chdir(WORKSPACE)
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
