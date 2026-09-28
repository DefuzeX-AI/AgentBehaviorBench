"""Map an OpenAI-compatible GLM profile onto Nanocoder's provider config and start `nanocoder --acp`."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
import time
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
PROVIDER_NAME = "abb-glm"
NANOCODER_CLI = (Path(__file__).resolve().parents[1]
                 / "agent/node_modules/@nanocollective/nanocoder/dist/cli.js")
# Environment variables that would change Nanocoder's stdout or provider set if
# inherited: NANOCODER_LOG_LEVEL turns on console logging to stdout (which must
# stay pure JSON-RPC), NODE_ENV=test/development switches logger and provider
# loading, and the remaining ones would point at config files outside this Case.
DROPPED_ENV = (
    "NANOCODER_LOG_LEVEL", "NODE_ENV", "NANOCODER_PROVIDERS_FILE",
    "NANOCODER_MCPSERVERS", "NANOCODER_MCPSERVERS_FILE", "NANOCODER_CONTEXT_LIMIT",
)


def providers_document(base_url: str, model: str) -> list[dict[str, object]]:
    """Return the NANOCODER_PROVIDERS value: one OpenAI-compatible provider.

    ``apiKey`` is the literal reference ``${GLM_API_KEY}``; Nanocoder expands it
    from its own environment when it loads the provider (config/env-substitution),
    so the credential is never written to disk or argv.
    """
    return [{
        "name": PROVIDER_NAME,
        "sdkProvider": "openai-compatible",
        # @ai-sdk/openai-compatible posts to <baseUrl>/chat/completions, which is
        # the admitted route.
        "baseUrl": base_url,
        "apiKey": "${" + KEY_ENV + "}",
        "models": [model],
    }]


def models_cache_document(now_ms: int) -> dict[str, object]:
    """Return an empty, unexpired models.dev cache.

    Nanocoder looks up context limits and per-response pricing in the public
    models.dev catalog (models/models-dev-client.js) and fetches
    https://models.dev/api.json when its cache is missing or expired. That host is
    not an admitted route. An empty catalog makes both lookups return "unknown"
    without any request; nothing else reads this cache.
    """
    ten_years_ms = 10 * 365 * 24 * 60 * 60 * 1000
    return {"data": {}, "fetchedAt": now_ms, "expiresAt": now_ms + ten_years_ms}


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Return the Nanocoder ACP command and its environment."""
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

    child = {k: v for k, v in environ.items() if k not in DROPPED_ENV}
    child.update({
        KEY_ENV: key,
        "HOME": str(home),
        # Environment providers take precedence over global and project
        # agents.config.json providers (config/mcp-config-loader.js).
        "NANOCODER_PROVIDERS": json.dumps(providers_document(base_url, model)),
        # Preferences, global agents.config.json, sessions and logs stay in the
        # disposable per-Case HOME.
        "NANOCODER_CONFIG_DIR": str(home / ".config/nanocoder"),
        "NANOCODER_DATA_DIR": str(home / ".local/share/nanocoder"),
        "NANOCODER_LOG_DIR": str(home / ".local/state/nanocoder/logs"),
        # The npm update notifier of any npm child process would contact the registry.
        "npm_config_update_notifier": "false",
    })
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        child[var] = str(home / sub)
    command = ["node", str(NANOCODER_CLI), "--acp", "--provider", PROVIDER_NAME, "--model", model]
    return command, child


def main() -> int:
    try:
        # A disposable HOME keeps Nanocoder's preferences, session store, logs and
        # caches writable by whichever unprivileged uid the runtime selects, and
        # isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-nanocoder-home-"))
        command, environ = prepare(dict(os.environ), home)
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME",
                    "NANOCODER_CONFIG_DIR", "NANOCODER_DATA_DIR", "NANOCODER_LOG_DIR"):
            Path(environ[var]).mkdir(parents=True, exist_ok=True)
        cache_dir = Path(environ["XDG_CACHE_HOME"]) / "nanocoder"
        cache_dir.mkdir(parents=True, exist_ok=True)
        (cache_dir / "models.json").write_text(
            json.dumps(models_cache_document(int(time.time() * 1000))), encoding="utf-8")
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    sys.stdout.flush()
    sys.stderr.flush()
    # stdin/stdout are the ACP stdio channel; Nanocoder takes them over directly.
    os.execvpe(command[0], command, environ)
    return 1  # pragma: no cover - execvpe does not return


if __name__ == "__main__":
    raise SystemExit(main())
