"""Map the selected OpenAI-compatible model profile onto LLxprt Code's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
# The published `llxprt` bin: a Node shim that starts the bundled Bun runtime on
# bundle/llxprt.js with stdio inherited, so ACP stdio reaches LLxprt unchanged.
LLXPRT_BIN = (Path(__file__).resolve().parents[1]
              / "source/packages/cli/bin/llxprt.mjs")
# Variables that would select another provider, credential, profile or storage
# root, or switch on debug output, if inherited from the container environment.
DROPPED_ENV = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "GOOGLE_CLOUD_PROJECT", "GOOGLE_CLOUD_LOCATION", "GOOGLE_APPLICATION_CREDENTIALS",
    "GOOGLE_GENAI_USE_VERTEXAI", "ANTHROPIC_API_KEY", "LLXPRT_CONFIG_HOME",
    "LLXPRT_DATA_HOME", "LLXPRT_CACHE_HOME", "LLXPRT_LOG_HOME", "LLXPRT_PROFILE",
    "LLXPRT_DEFAULT_PROVIDER", "LLXPRT_DEFAULT_MODEL", "DEBUG", "DEBUG_MODE",
)
# User settings written to the disposable config directory.
SETTINGS = {
    # Auto-update and update notifications query the npm registry.
    "enableAutoUpdate": False,
    "enableAutoUpdateNotification": False,
    "ui": {"usageStatisticsEnabled": False},
    # OpenTelemetry export stays off (upstream default, stated explicitly).
    "telemetry": {"enabled": False},
    # No IDE companion runs in the container.
    "ide": {"enabled": False, "hasSeenNudge": True},
}


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Return the LLxprt ACP command and its environment."""
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
        # LLxprt's openai provider falls back to OPENAI_API_KEY when no --key,
        # --keyfile, keyring entry or profile key is given, so the credential
        # never appears in argv or on disk.
        "OPENAI_API_KEY": key,
        "HOME": str(home),
        # No D-Bus secret service exists in the container; use the file fallback
        # instead of probing the OS keyring.
        "LLXPRT_DISABLE_OS_KEYRING": "1",
        # The npm update notifier of any npm child process would contact the registry.
        "npm_config_update_notifier": "false",
        "NO_UPDATE_NOTIFIER": "1",
    })
    # LLxprt resolves its config, data, cache and log roots through env-paths,
    # which follows the XDG variables on Linux.
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        child[var] = str(home / sub)
    command = [
        "node", str(LLXPRT_BIN), "--experimental-acp",
        # The openai provider posts to <baseurl>/chat/completions with the
        # OpenAI SDK, which is the admitted shared route.
        "--provider", "openai", "--baseurl", base_url, "--model", model,
    ]
    return command, child


def seed_home(environ: dict[str, str]) -> None:
    """Create LLxprt's directories, its user settings and an empty model catalog."""
    for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
        Path(environ[var]).mkdir(parents=True, exist_ok=True)
    config_dir = Path(environ["XDG_CONFIG_HOME"]) / "llxprt-code"
    config_dir.mkdir(parents=True, exist_ok=True)
    (config_dir / "settings.json").write_text(json.dumps(SETTINGS, indent=2), encoding="utf-8")
    # LLxprt's model registry (core/src/models/registry.ts) reads model metadata
    # from <cache>/models.json and fetches https://models.dev/api.json when the
    # file is missing or older than seven days. That host is not admitted. A fresh
    # empty catalog is valid for its schema, so no request is made; context and
    # pricing metadata for the selected model are then unknown.
    cache_dir = Path(environ["XDG_CACHE_HOME"]) / "llxprt-code"
    cache_dir.mkdir(parents=True, exist_ok=True)
    (cache_dir / "models.json").write_text("{}", encoding="utf-8")


def main() -> int:
    try:
        # A disposable HOME keeps LLxprt's settings, sessions, logs and caches
        # writable by whichever unprivileged uid the runtime selects, and
        # isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-llxprt-home-"))
        command, environ = prepare(dict(os.environ), home)
        seed_home(environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    sys.stdout.flush()
    sys.stderr.flush()
    # stdin/stdout are the ACP stdio channel; LLxprt takes them over directly.
    os.execvpe(command[0], command, environ)
    return 1  # pragma: no cover - execvpe does not return


if __name__ == "__main__":
    raise SystemExit(main())
