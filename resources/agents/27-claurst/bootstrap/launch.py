"""Map an OpenAI-compatible GLM profile onto Claurst's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
CLAURST_BIN = "/opt/claurst/bin/claurst"
# Claurst's generic OpenAI-compatible provider. Unlike the built-in `zhipu`
# provider it uses api_base verbatim (no `/v1` suffix is appended) and posts to
# `<api_base>/chat/completions`, which is exactly the admitted GLM route.
PROVIDER_ID = "custom-openai"
PROVIDER_KEY_ENV = "CUSTOM_OPENAI_API_KEY"


def settings(base_url: str, model: str) -> dict[str, object]:
    """Return settings.json selecting the GLM endpoint; the key stays in the environment."""
    # Claurst silently falls back to default settings (Anthropic) when this
    # file does not deserialize, and its `config` object has no serde
    # defaults, so every non-optional field is written with its default value.
    config = {
        "provider": PROVIDER_ID,
        "model": model,
        "permission_mode": "default",
        "theme": "default",
        "auto_compact": True,
        "compact_threshold": 0.0,
        "verbose": False,
        "output_format": "text",
        "mcp_servers": [],
        "allowed_tools": [],
        "disallowed_tools": [],
        "env": {},
        "enable_all_mcp_servers": False,
        "disable_claude_mds": False,
    }
    return {
        "provider": PROVIDER_ID,
        "providers": {PROVIDER_ID: {"api_base": base_url, "enabled": True}},
        "config": config,
        "hasCompletedOnboarding": True,
    }


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Return the ACP command, child environment and settings without persisting secrets."""
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    if not base_url:
        raise ValueError(f"{BASE_URL_ENV} is required")
    if not model:
        raise ValueError(f"{MODEL_ENV} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    child = {
        **environ,
        # custom-openai reads its credential from this variable at request time.
        PROVIDER_KEY_ENV: key,
        # models.dev catalog refresh at startup is outside the admitted route.
        "CLAURST_DISABLE_MODELS_FETCH": "1",
        "CLAURST_DISABLE_NONESSENTIAL_TRAFFIC": "1",
    }
    return [CLAURST_BIN, "acp"], child, settings(base_url, model)


def main() -> int:
    try:
        command, environ, config = prepare(dict(os.environ))
        # A disposable HOME/CLAURST_HOME keeps settings, sessions and caches
        # writable by whichever unprivileged uid the runtime selects, and
        # isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-claurst-home-"))
        claurst_home = home / ".claurst"
        claurst_home.mkdir()
        (claurst_home / "settings.json").write_text(json.dumps(config, indent=2))
        environ["HOME"] = str(home)
        environ["CLAURST_HOME"] = str(claurst_home)
        for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                         ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
            (home / sub).mkdir(parents=True, exist_ok=True)
            environ[var] = str(home / sub)
        # WebFetch/WebSearch run natively. Their non-model traffic goes to ABB's
        # egress observer (declared tool routes are forwarded and recorded).
        sys.stdout.flush()
        os.execve(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
