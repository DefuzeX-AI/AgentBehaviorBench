"""Start Dirac's native ACP server with ABB's shared model selection."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
BINARY = "/opt/agent/agent/node_modules/.bin/dirac"
WORKSPACE = "/home/agent/workspace"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    for name in (KEY_ENV, BASE_ENV, MODEL_ENV):
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    base = environ[BASE_ENV].rstrip("/")
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError(f"{BASE_ENV} must be an HTTPS URL without credentials, query or fragment")
    native_home = home / ".dirac"
    child = {
        **environ,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "DIRAC_DIR": str(native_home),
        "DIRAC_DATA_DIR": str(native_home / "data"),
        "DIRAC_LOG_DIR": str(native_home / "data/logs"),
        # 'openai' is Dirac's native generic Chat Completions provider ID.
        "DIRAC_PROVIDER": "openai",
        "DIRAC_MODEL": environ[MODEL_ENV],
        "DIRAC_BASE_URL": base,
        "DIRAC_API_KEY": environ[KEY_ENV],
    }
    command = [BINARY, "--acp", "--config", str(native_home), "--cwd", WORKSPACE]
    return command, child


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-dirac-"))
        command, child = prepare(dict(os.environ), home)
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
