"""Configure OpenBitFun from ABB_AGENT_MODEL_* then exec native ACP stdio server."""
from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
OPENBITFUN = os.environ.get("ABB_OPENBITFUN_BIN", "/usr/local/bin/openbitfun")


def _require(environ: dict[str, str]) -> tuple[str, str, str]:
    key = environ.get(KEY_ENV, "").strip()
    base = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    for name, value in ((KEY_ENV, key), (BASE_URL_ENV, base), (MODEL_ENV, model)):
        if not value:
            raise ValueError(f"{name} is required")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    if any(c.isspace() for c in model):
        raise ValueError(f"{MODEL_ENV} must not contain whitespace")
    return key, base, model


def prepare(environ: dict[str, str]):
    key, base, model = _require(environ)
    child = {k: v for k, v in environ.items() if not k.startswith("ABB_AGENT_MODEL")}
    home = Path(tempfile.mkdtemp(prefix="abb-openbitfun-"))
    (home / ".config").mkdir(parents=True, exist_ok=True)
    for relative in (".local/share", ".cache", ".local/state"):
        (home / relative).mkdir(parents=True, exist_ok=True)
    child["HOME"] = str(home)
    child["XDG_CONFIG_HOME"] = str(home / ".config")
    child["XDG_DATA_HOME"] = str(home / ".local" / "share")
    child["XDG_CACHE_HOME"] = str(home / ".cache")
    child["XDG_STATE_HOME"] = str(home / ".local" / "state")
    app_json = home / ".config" / "openbitfun" / "config" / "app.json"
    return [OPENBITFUN, "acp", "serve"], child, app_json, key, base, model


def _inject_model(app_json: Path, key: str, base: str, model: str) -> None:
    if not app_json.is_file():
        raise ValueError("OpenBitFun did not create config/app.json")
    cfg = json.loads(app_json.read_text(encoding="utf-8"))
    model_id = "abb-primary"
    cfg.setdefault("ai", {})
    cfg["ai"]["models"] = [
        {
            "id": model_id,
            "name": "ABB Intercepted",
            "provider": "openai",
            "api_key": key,
            "base_url": base,
            "request_url": f"{base}/chat/completions",
            "model_name": model,
            "enabled": True,
            "is_default": True,
            "category": "code_specialized",
            "capabilities": ["text_chat", "function_calling"],
            "auth": {"type": "api_key"},
        }
    ]
    defaults = cfg["ai"].setdefault("default_models", {})
    defaults["primary"] = model_id
    defaults["fast"] = model_id
    cfg["last_modified"] = int(time.time() * 1000)
    app_json.write_text(json.dumps(cfg, indent=2), encoding="utf-8")


def main() -> None:
    command, child, app_json, key, base, model = prepare(dict(os.environ))
    subprocess.run(
        [OPENBITFUN, "acp", "doctor"],
        env=child,
        check=False,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    _inject_model(app_json, key, base, model)
    os.execvpe(command[0], command, child)


if __name__ == "__main__":
    main()
