"""Map an OpenAI-compatible GLM profile onto Kilo Code CLI's native ACP server."""
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
PROVIDER_ID = "glm"
# `kilo acp` starts Kilo's HTTP server on loopback and bridges ACP onto its
# REST/SSE API. The port is pinned so network/rules.toml can admit exactly it.
SERVER_HOST = "127.0.0.1"
SERVER_PORT = "4096"

# Kilo contacts several services at startup besides the model provider. Each
# one is outside the evaluated model route, so the interceptor would reject the
# trace as undeclared egress. These upstream switches turn them off.
QUIET_ENV = {
    "KILO_DISABLE_MODELS_FETCH": "1",  # models.dev catalog download
    "KILO_TELEMETRY_LEVEL": "off",  # PostHog product telemetry
    "KILO_DISABLE_AUTOUPDATE": "1",
    "KILO_DISABLE_SESSION_INGEST": "1",  # cloud session sync
    "KILO_DISABLE_PRESENCE": "1",
    "KILO_DISABLE_SHARE": "1",
    "KILO_DISABLE_DEFAULT_PLUGINS": "1",  # plugins are fetched from npm at runtime
    "KILO_DISABLE_LSP_DOWNLOAD": "1",
    "KILO_DISABLE_CODEBASE_INDEXING": "1",  # needs an embedding service
    "KILO_DISABLE_CLAUDE_CODE": "1",  # do not import ~/.claude settings/skills
    "KILO_DISABLE_EXTERNAL_SKILLS": "1",
}


def config(base_url: str, model: str) -> dict:
    """Return Kilo's global config: one OpenAI-compatible GLM provider, nothing else."""
    return {
        "$schema": "https://app.kilo.ai/config.json",
        # ACP session/new does not choose a model, so the default must be GLM.
        "model": f"{PROVIDER_ID}/{model}",
        "small_model": f"{PROVIDER_ID}/{model}",
        "autoupdate": False,
        "share": "disabled",
        # Only this provider is loaded; the built-in Kilo gateway (api.kilo.ai)
        # and other catalog providers are never contacted.
        "enabled_providers": [PROVIDER_ID],
        "provider": {
            PROVIDER_ID: {
                # Bundled in the Kilo binary; no runtime npm install happens.
                "npm": "@ai-sdk/openai-compatible",
                "name": "Zhipu GLM",
                # Kilo substitutes {env:...} at load time, so the key is not
                # written to disk.
                "options": {"baseURL": base_url, "apiKey": "{env:" + KEY_ENV + "}"},
                "models": {model: {"name": model}},
            }
        },
        # The title agent starts a second background model call after the first
        # turn; the one-shot worker closes ACP before it finishes and the trace
        # records a cut request. Removing the agent skips title generation.
        "agent": {"title": {"disable": True}},
    }


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Write Kilo's config under a disposable HOME and return the ACP command and env."""
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

    xdg = {
        "XDG_CONFIG_HOME": home / ".config",
        "XDG_DATA_HOME": home / ".local/share",
        "XDG_STATE_HOME": home / ".local/state",
        "XDG_CACHE_HOME": home / ".cache",
    }
    for path in xdg.values():
        path.mkdir(parents=True, exist_ok=True)
    (xdg["XDG_CONFIG_HOME"] / "kilo").mkdir()
    (xdg["XDG_CONFIG_HOME"] / "kilo/kilo.json").write_text(json.dumps(config(base_url, model), indent=2))

    child = {
        **environ,
        **QUIET_ENV,
        **{name: str(path) for name, path in xdg.items()},
        "HOME": str(home),
        KEY_ENV: key,
    }
    command = [str(Path(__file__).resolve().parents[1] / "agent/node_modules/.bin/kilo"), "acp", "--hostname", SERVER_HOST, "--port", SERVER_PORT]
    return command, child


def main() -> int:
    try:
        # A disposable HOME keeps Kilo's config, database and logs writable by
        # whichever unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-kilo-home-"))
        command, environ = prepare(dict(os.environ), home)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
