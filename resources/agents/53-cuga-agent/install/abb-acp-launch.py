"""ABB outer launcher for CUGA's inbound ACP stdio agent (modelled on the other ACP unit launchers).

Maps ABB's shared model selection (ABB_AGENT_MODEL_API_KEY / ABB_AGENT_MODEL_BASE_URL / ABB_AGENT_MODEL;
every shared profile is an OpenAI-compatible Chat Completions endpoint) onto CUGA's documented OpenAI configuration
(README "Use your own inference endpoint"): AGENT_SETTING_CONFIG=settings.openai.toml, OPENAI_BASE_URL, OPENAI_API_KEY,
MODEL_NAME. Then execs `<venv>/bin/cuga-acp`.
Per-case disposable HOME and CUGA_DBS_DIR (the package default dbs/ dir lives in site-packages and is not writable).
Evolve (optional external MCP memory service, not deployed here) is switched off via its documented dynaconf env toggle.
Standard library only.
"""
from __future__ import annotations

import os
import sys
import tempfile
from urllib.parse import urlsplit

KEY_ENV, BASE_URL_ENV, MODEL_ENV = "ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"
CUGA_ACP = os.environ.get("ABB_CUGA_ACP", "/opt/cuga-venv/bin/cuga-acp")


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
    child = {**environ, "AGENT_SETTING_CONFIG": "settings.openai.toml", "OPENAI_BASE_URL": base_url,
             "OPENAI_API_KEY": key, "MODEL_NAME": model, "DYNACONF_EVOLVE__ENABLED": "false"}
    # ABB's ACP adapter passes only an env allowlist to the agent (agentbench/adapter/acp/process.py child_environment),
    # so image ENV such as FASTEMBED_CACHE_PATH / HF_HUB_OFFLINE is dropped. Without them the policy store's local
    # embedding model cannot be loaded and NO .cuga policy is registered.
    child.setdefault("FASTEMBED_CACHE_PATH", "/opt/fastembed-cache")
    child.setdefault("HF_HUB_OFFLINE", "1")
    # onnxruntime (fastembed's backend) otherwise sends telemetry to mobile.events.data.microsoft.com, which egress refuses.
    child.setdefault("ORT_DISABLE_TELEMETRY", "1")
    child.pop("OPENAI_API_BASE", None)
    return [CUGA_ACP], child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        home = tempfile.mkdtemp(prefix="abb-cuga-home-")
        environ["HOME"] = home
        dbs = os.path.join(home, "dbs")
        os.makedirs(dbs, exist_ok=True)
        environ["CUGA_DBS_DIR"] = dbs
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            environ.pop(var, None)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        print(str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
