"""Configure the pinned native fast-agent ACP server from ABB's model selection."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
BINARY = "/opt/fast-agent-venv/bin/fast-agent-acp"
WORKSPACE = "/home/agent/workspace"

# Native YAML interpolation keeps the credential out of files and argv.
CONFIG = """generic:
  api_key: ${ABB_AGENT_MODEL_API_KEY}
  base_url: ${ABB_AGENT_MODEL_BASE_URL}
"""


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    for name in (KEY_ENV, BASE_ENV, MODEL_ENV):
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    base = urlsplit(environ[BASE_ENV])
    if (base.scheme != "https" or not base.hostname or base.username or base.password
            or base.query or base.fragment):
        raise ValueError(f"{BASE_ENV} must be an HTTPS URL without credentials, query or fragment")

    # Each ACP process gets its own config, permission store, sessions and caches.
    # A real --home preserves upstream permission prompts; --no-home disables them.
    child = dict(environ)
    child.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
    })
    command = [BINARY, "--config-path", str(home / "fast-agent.yaml"),
               "--home", str(home / ".fast-agent"), "--workspace", WORKSPACE,
               "--model", "generic." + environ[MODEL_ENV], "--shell"]
    return command, child


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-fast-agent-"))
        command, child = prepare(dict(os.environ), home)
        (home / "fast-agent.yaml").write_text(CONFIG, encoding="utf-8")
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
