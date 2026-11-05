"""Configure an isolated native runtime, then host Synergy's original ACP command."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

REQUIRED = ("ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL")


def prepare(environ: dict[str, str], home: Path):
    for name in REQUIRED:
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    base = environ["ABB_AGENT_MODEL_BASE_URL"]
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("ABB_AGENT_MODEL_BASE_URL must be a credential-free HTTPS URL")
    model = environ["ABB_AGENT_MODEL"]
    child = {**environ, "HOME": str(home), "SYNERGY_HOME": str(home),
             "XDG_CONFIG_HOME": str(home / ".config"), "XDG_DATA_HOME": str(home / ".local/share"),
             "XDG_CACHE_HOME": str(home / ".cache"), "SYNERGY_DISABLE_MODELS_FETCH": "1"}
    # Only same-container IPC bypasses the model proxy; model hosts remain proxied.
    for key in ("NO_PROXY", "no_proxy"):
        values = [x for x in child.get(key, "").split(",") if x]
        child[key] = ",".join(dict.fromkeys([*values, "127.0.0.1", "localhost"]))
    documents = {
        "10-models.jsonc": {"model": "abb/" + model},
        "20-providers.jsonc": {"provider": {"abb": {
            "name": "ABB selected model", "npm": "@ai-sdk/openai-compatible",
            "options": {"baseURL": base, "apiKey": "{env:ABB_AGENT_MODEL_API_KEY}"},
            "models": {model: {"id": model, "name": model,
                "limit": {"context": 131072, "output": 8192}}}}}},
        "60-agents.jsonc": {"default_agent": "forge"},
        # ABB's nonroot Docker worker is the OS isolation boundary. Nested
        # bubblewrap cannot create namespaces under its standard policy.
        # Keep native tool approvals; do not switch to the full_access profile.
        "80-permissions.jsonc": {"controlProfile": "guarded", "sandbox": {"enabled": False}},
    }
    command = ["bun", "/opt/agent/bootstrap/acp.ts", "acp",
               "--cwd", "/home/agent/workspace", "--hostname", "127.0.0.1", "--port", "0"]
    return command, child, documents


def main():
    try:
        home = Path(tempfile.mkdtemp(prefix=".abb-synergy-", dir="/home/agent"))
        command, child, documents = prepare(dict(os.environ), home)
        directory = home / ".synergy/config/synergy.d"
        directory.mkdir(parents=True, mode=0o700)
        for name, document in documents.items():
            path = directory / name
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
            path.chmod(0o600)
        os.chdir("/home/agent/workspace")
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        print(str(exc).replace(os.environ.get(REQUIRED[0]) or "\0", "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
