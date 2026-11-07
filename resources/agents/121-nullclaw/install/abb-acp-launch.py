"""ABB outer launcher for NullClaw's ACP stdio adapter (modelled on the other ACP unit launchers).

NullClaw reads model configuration only from ~/.nullclaw/config.json (docs/en/configuration.md "Config File Path"),
so at container start this launcher:
  1. reads ABB's shared model selection ABB_AGENT_MODEL_API_KEY / ABB_AGENT_MODEL_BASE_URL / ABB_AGENT_MODEL
     (every shared profile is an OpenAI-compatible Chat Completions endpoint);
  2. points HOME and NULLCLAW_HOME at a disposable per-Case directory and writes ~/.nullclaw/config.json (0600) with
     the documented "Minimal Working Config" / "Recommended Security Config" shape:
       models.providers.<p>.{api_key, base_url}; agents.defaults.model.primary = "<p>/<model>";
       memory {backend: "sqlite", auto_save: true}; autonomy {level: "supervised", workspace_only: true,
       max_actions_per_hour: 20}.
     <p> is the built-in "deepseek" provider when the base URL host is api.deepseek.com, otherwise
     "custom:<base_url>" (README: any OpenAI-compatible API). The key is never baked into the image;
  3. ABB model interception trust: the Zig std HTTP client reads the system CA bundle, not SSL_CERT_FILE, so when ABB
     provides SSL_CERT_FILE the launcher appends that PEM to the (agent-writable, see Dockerfile) system bundle once;
  4. execs `nullclaw acp` (newline-delimited JSON-RPC on stdio; each session/prompt runs `nullclaw agent invoke`
     with the ACP session cwd as workspace).
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

KEY_ENV, BASE_URL_ENV, MODEL_ENV = "ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"
BINARY = os.environ.get("ABB_NULLCLAW_BIN", "/usr/local/bin/nullclaw")
SYSTEM_BUNDLE = Path("/etc/ssl/certs/ca-certificates.crt")


def trust_interceptor(environ):
    pem_path = environ.get("SSL_CERT_FILE", "").strip()
    if not pem_path or not Path(pem_path).is_file():
        return
    try:
        pem = Path(pem_path).read_text(encoding="utf-8")
        current = SYSTEM_BUNDLE.read_text(encoding="utf-8") if SYSTEM_BUNDLE.exists() else ""
        if pem.strip() and pem.strip() not in current:
            with SYSTEM_BUNDLE.open("a", encoding="utf-8") as fh:
                fh.write("\n" + pem.strip() + "\n")
    except OSError as exc:
        print(f"abb-acp-launch: could not extend system CA bundle: {exc}", file=sys.stderr)


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
    provider = "deepseek" if parsed.hostname == "api.deepseek.com" else f"custom:{base_url}"
    config = {
        "models": {"providers": {provider: {"api_key": key, "base_url": base_url}}},
        "agents": {"defaults": {"model": {"primary": f"{provider}/{model}"}}},
        "memory": {"backend": "sqlite", "auto_save": True},
        "autonomy": {"level": "supervised", "workspace_only": True, "max_actions_per_hour": 20},
    }
    home = Path(tempfile.mkdtemp(prefix="abb-nullclaw-home-"))
    nc = home / ".nullclaw"
    nc.mkdir(mode=0o700)
    cfg = nc / "config.json"
    fd = os.open(cfg, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(config, fh, indent=2)
    child = dict(environ)
    child["HOME"] = str(home)
    child["NULLCLAW_HOME"] = str(nc)
    child.pop("NULLCLAW_WORKSPACE", None)
    trust_interceptor(environ)
    return [BINARY, "acp"], child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        print(str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
