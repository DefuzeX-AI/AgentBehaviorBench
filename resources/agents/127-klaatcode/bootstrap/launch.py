"""Prepare a fresh native home, then start the unchanged ACP implementation."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

REQUIRED = ("ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL")


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict]:
    for name in REQUIRED:
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    parsed = urlsplit(environ[REQUIRED[1]])
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("ABB_AGENT_MODEL_BASE_URL must be a credential-free HTTPS URL")
    if not re.search(r"/v\d+$", parsed.path.rstrip("/")):
        raise ValueError("Klaat Code requires a versioned model base URL (for DeepSeek, configure DEEPSEEK_BASE_URL=https://api.deepseek.com/v1)")
    child = {**environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
             "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache"),
             "KLAATAI_TELEMETRY": "0", "DO_NOT_TRACK": "1",
             # ACP requires a nonempty native token even with a custom endpoint.
             # This marker is not an account credential. Chat uses ABB's real key
             # via the native setCustomEndpoint API; hosted graph services are absent.
             "KLAATAI_API_KEY": "abb-custom-endpoint-no-klaatu-account"}
    return ["bun", "/opt/agent/bootstrap/acp.ts"], child, {"telemetry": "off"}


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-klaatcode-"))
        command, child, config = prepare(dict(os.environ), home)
        native = home / ".klaatai"
        native.mkdir(mode=0o700)
        path = native / "config.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        path.chmod(0o600)
        os.chdir("/home/agent/workspace")
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(REQUIRED[0]) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
