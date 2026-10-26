"""ABB outer launcher for bub's ACP server (bub-acp-server plugin).

Maps ABB's shared model selection (ABB_AGENT_MODEL_API_KEY / ABB_AGENT_MODEL_BASE_URL / ABB_AGENT_MODEL;
every shared profile is an OpenAI-compatible Chat Completions endpoint) onto bub's AgentSettings
(bub.builtin.settings): model=openai:<model>, api_key, api_base. Republic's `openai` provider defaults to the
Responses API, so the Chat Completions format is requested via client_args={"api_format":"chat"}.
The settings go into the per-Case `$BUB_HOME/config.yml` (0600; bub loads it at startup, bub.framework) rather
than BUB_* environment variables, and ABB_AGENT_MODEL_* are removed from bub's environment: bub's bash tool
inherits that environment, and a listing such as `env | sed 's/=.*//'` would otherwise show credential names.
A disposable BUB_HOME/HOME per case, then exec `/opt/bub-venv/bin/bub acp` (stdio). Standard library only.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from urllib.parse import urlsplit

KEY_ENV, BASE_URL_ENV, MODEL_ENV = "ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"
BUB = os.environ.get("ABB_BUB_BIN", "/opt/bub-venv/bin/bub")


def prepare(environ):
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    for name, value in ((KEY_ENV, key), (BASE_URL_ENV, base_url), (MODEL_ENV, model)):
        if not value:
            raise ValueError(f"{name} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    child = {k: v for k, v in environ.items() if not k.startswith(("BUB_", "ABB_AGENT_MODEL"))}
    settings = {"model": f"openai:{model}", "api_key": key, "api_base": base_url,
                "client_args": {"api_format": "chat"}}
    return [BUB, "acp"], child, settings


def main() -> int:
    try:
        command, environ, settings = prepare(dict(os.environ))
        home = tempfile.mkdtemp(prefix="abb-bub-home-")
        environ["HOME"] = home
        environ["BUB_HOME"] = os.path.join(home, ".bub")
        os.makedirs(environ["BUB_HOME"], mode=0o700)
        # JSON is valid YAML; bub reads ~/.bub/config.yml (HOME is the disposable directory above).
        fd = os.open(os.path.join(environ["BUB_HOME"], "config.yml"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(settings, fh)
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            environ.pop(var, None)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        print(str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
