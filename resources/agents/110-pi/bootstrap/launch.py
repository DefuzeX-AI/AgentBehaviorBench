#!/usr/bin/env python3
"""Start Pi's native ACP server for one ABB Case.

Pi reads custom providers from ``~/.pi/agent/models.json``. The launcher writes one
provider entry pointing at the runtime model endpoint, keeping the key out of the
file: ``apiKey`` holds the *name* of an environment variable, which Pi resolves at
request time. Then it replaces itself with ``pi --acp``.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"

PI = "/usr/local/bin/pi"
KEY_VARIABLE = "ABB_PI_MODEL_KEY"
PROVIDER = "abb"


def log(message: str) -> None:
    sys.stderr.write(f"[pi-launch] {message}\n")
    sys.stderr.flush()


def write_models(base_url: str, model: str) -> Path:
    """Write the provider entry Pi reads, naming an env var instead of the key."""
    home = Path(os.environ.get("HOME") or "/home/agent")
    target = home / ".pi" / "agent" / "models.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    document = {
        "providers": {
            PROVIDER: {
                "api": "openai-completions",
                "baseUrl": base_url,
                "apiKey": KEY_VARIABLE,
                "models": [{"id": model, "name": model}],
            }
        }
    }
    target.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
    target.chmod(0o600)
    return target


def main() -> None:
    api_key = os.environ.get(KEY_ENV, "").strip()
    base_url = os.environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = os.environ.get(MODEL_ENV, "").strip()
    log(f"model={model or '-'} base_url={base_url or '-'} "
        f"key={'set' if api_key else 'missing'} proxy={os.environ.get('HTTPS_PROXY', '-')}")
    if not api_key or not base_url or not model:
        log("missing model settings; expected ABB_AGENT_MODEL_API_KEY, "
            "ABB_AGENT_MODEL_BASE_URL and ABB_AGENT_MODEL")
        raise SystemExit(1)

    target = write_models(base_url, model)
    log(f"provider {PROVIDER!r} written to {target} (key read from ${KEY_VARIABLE})")

    environ = dict(os.environ)
    environ[KEY_VARIABLE] = api_key
    environ.setdefault("PI_NO_UPDATE_CHECK", "1")
    argv = [PI, "--acp", "--provider", PROVIDER, "--model", model]
    log(f"exec {' '.join(argv[:1] + argv[1:4])} …")
    os.execve(PI, argv, environ)


if __name__ == "__main__":
    main()
