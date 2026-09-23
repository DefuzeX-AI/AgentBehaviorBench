"""Map an OpenAI-compatible GLM profile onto Kode's model-profile config and start its ACP server."""
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
# Kode's built-in provider id for Zhipu's OpenAI-compatible GLM Coding Plan
# endpoint; it selects the Chat Completions adapter for glm-5.x models.
PROVIDER = "glm-coding"
AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
KODE_ENTRY = AGENT_DIR / "node_modules/@shareai-lab/kode/dist/index.js"


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict]:
    """Return the Kode ACP command, its environment and Kode's global config."""
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

    config = {
        "numStartups": 1,
        "theme": "dark",
        "verbose": False,
        "preferredNotifChannel": "notifications_disabled",
        "hasCompletedOnboarding": True,
        "autoUpdaterStatus": "disabled",
        "primaryProvider": PROVIDER,
        # Kode reads the credential only from the model profile (there is no
        # environment-variable reference for custom profiles), so it is written
        # to a 0600 file in the disposable per-Case HOME, never to the image,
        # argv or this unit. Under ABB interception this is the runtime's
        # surrogate credential, not the upstream key.
        "modelProfiles": [{
            "name": model,
            "provider": PROVIDER,
            "modelName": model,
            "baseURL": base_url,
            "apiKey": key,
            "maxTokens": 8192,
            "contextLength": 128000,
            "isActive": True,
            "createdAt": int(time.time() * 1000),
        }],
        # ACP session/new does not pick a model; every Kode role uses GLM.
        "modelPointers": {"main": model, "task": model, "compact": model, "quick": model},
    }
    child = {
        **environ,
        # Skips the npm registry version check (autoUpdater.assertMinVersion);
        # registry.npmjs.org is not on the admitted route.
        "KODE_OFFLINE": "1",
        "npm_config_offline": "true",
        "npm_config_update_notifier": "false",
    }
    # Same entry point `kode-acp` falls back to when no native binary was
    # downloaded; `--acp` selects the ACP stdio server.
    command = ["node", str(KODE_ENTRY), "--acp"]
    return command, child, config


def main() -> int:
    try:
        command, environ, config = prepare(dict(os.environ))
        # A disposable HOME keeps Kode's config, ACP session files and logs
        # writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-kode-home-"))
        config_dir = home / ".kode"
        config_dir.mkdir(mode=0o700)
        path = config_dir / "config.json"
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(config, handle, indent=2)
        environ["HOME"] = str(home)
        environ["KODE_CONFIG_DIR"] = str(config_dir)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
