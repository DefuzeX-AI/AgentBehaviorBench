"""Create isolated native settings and exec the unchanged iCode ACP command."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit

REQUIRED = ("ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL")
PROFILE_ID = "abb00000000000000000000000000495"
PROVIDERS = {"deepseek": "deepseek-openai", "openrouter": "openai", "glm": "glm-openai"}


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict]:
    for name in REQUIRED:
        if not environ.get(name, "").strip():
            raise ValueError(f"{name} is required")
    provider = PROVIDERS.get(environ.get("ABB_AGENT_MODEL_PROVIDER", ""))
    if provider is None:
        raise ValueError("ABB_AGENT_MODEL_PROVIDER must be deepseek, openrouter or glm")
    base = environ["ABB_AGENT_MODEL_BASE_URL"]
    parsed = urlsplit(base)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment):
        raise ValueError("ABB_AGENT_MODEL_BASE_URL must be a credential-free HTTPS URL")
    child = {**environ, "HOME": str(home), "XDG_CONFIG_HOME": str(home / ".config"),
             "XDG_DATA_HOME": str(home / ".local/share"), "XDG_CACHE_HOME": str(home / ".cache"),
             "CHRYS_MODEL_PROFILE": PROFILE_ID, "CHRYS_UPDATE_CHECK": "0"}
    profile = {"id": PROFILE_ID, "name": "ABB selected model", "provider": provider,
               "api_style": "chat_completions", "model_id": environ["ABB_AGENT_MODEL"],
               "base_url": base, "api_key": "{{ABB_AGENT_MODEL_API_KEY}}"}
    command = ["/opt/icode-venv/bin/icode", "acp", "--agent", "Code", "--approval", "manual",
               "--workdir", "/home/agent/workspace"]
    return command, child, profile


def main() -> int:
    try:
        home = Path(tempfile.mkdtemp(prefix="abb-icode-"))
        command, child, profile = prepare(dict(os.environ), home)
        models = home / ".chrys/models"
        models.mkdir(parents=True, mode=0o700)
        path = models / f"{PROFILE_ID}.yaml"
        # JSON is a YAML subset; native iCode resolves the key's env template.
        path.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
        path.chmod(0o600)
        os.chdir("/home/agent/workspace")
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(REQUIRED[0]) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
