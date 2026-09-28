"""Map an OpenAI-compatible GLM profile onto OpenCode's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
PROVIDER_ID = "glm"
DISTRIBUTION = Path(__file__).resolve().parents[1] / "agent"
# `opencode acp` is a thin ACP front end over OpenCode's own HTTP server,
# started in-process on this loopback port (see network/rules.toml).
SERVER_HOST = "127.0.0.1"
SERVER_PORT = "4096"

# Every OPENCODE_DISABLE_* switch below closes a startup/background network call
# that is not an agent tool (catalog, updates, sharing, plugin discovery).
FLAGS = {
    # Offer the websearch tool (keyless Exa MCP endpoint, a declared tool route in
    # network/rules.toml); upstream enables it by default only for its own provider.
    "OPENCODE_ENABLE_EXA": "1",
    "OPENCODE_DISABLE_MODELS_FETCH": "1",  # models.dev catalog download
    "OPENCODE_DISABLE_AUTOUPDATE": "1",  # release check
    "OPENCODE_DISABLE_SHARE": "1",  # session sharing service
    "OPENCODE_DISABLE_DEFAULT_PLUGINS": "1",  # built-in auth plugins for other providers
    "OPENCODE_PURE": "1",  # no external plugin discovery/installation
    "OPENCODE_DISABLE_LSP_DOWNLOAD": "1",  # language servers fetched on demand
    "OPENCODE_DISABLE_CLAUDE_CODE": "1",  # do not import ~/.claude prompts/skills
    "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
}


def config(base_url: str, model: str) -> dict:
    """Return OpenCode's native config; the key stays an {env:...} reference."""
    ref = f"{PROVIDER_ID}/{model}"
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": ref,
        "small_model": ref,
        "enabled_providers": [PROVIDER_ID],
        "autoupdate": False,
        "share": "disabled",
        # The title agent starts a second, background model call after the
        # first turn; the one-shot worker closes ACP before it finishes.
        "agent": {"title": {"disable": True}},
        "provider": {
            PROVIDER_ID: {
                # Bundled in the OpenCode binary, so no provider package is fetched.
                "npm": "@ai-sdk/openai-compatible",
                "name": "Zhipu GLM",
                "options": {"baseURL": base_url, "apiKey": "{env:" + KEY_ENV + "}"},
                "models": {model: {"name": model}},
            }
        },
    }


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict]:
    """Return the OpenCode ACP command, environment and config without persisting secrets."""
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

    # OpenCode resolves {env:GLM_API_KEY} itself, so the key is passed only via
    # the environment and never lands in argv or in the written config file.
    child = {**environ, KEY_ENV: key, **FLAGS}
    # The server address is pinned so the loopback tool route stays exact.
    command = [str(DISTRIBUTION / "node_modules/.bin/opencode"), "acp",
               "--hostname", SERVER_HOST, "--port", SERVER_PORT]
    return command, child, config(base_url, model)


def seed_config_dir(config_dir: Path, settings: dict) -> None:
    """Write opencode.json and mark the plugin dependency as already installed.

    At startup OpenCode runs a background `npm install @opencode-ai/plugin` in
    its config dir unless node_modules exists and package.json/package-lock.json
    already declare and lock it. The pinned package is installed in the image, so
    the lock is copied and node_modules points there; no registry call happens.
    """
    config_dir.mkdir(parents=True)
    (config_dir / "opencode.json").write_text(json.dumps(settings, indent=2))
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(DISTRIBUTION / name, config_dir / name)
    (config_dir / "node_modules").symlink_to(DISTRIBUTION / "node_modules")


def main() -> int:
    try:
        command, environ, settings = prepare(dict(os.environ))
        # A disposable HOME keeps OpenCode's config, SQLite session store and
        # cache writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-opencode-home-"))
        xdg = {
            "XDG_CONFIG_HOME": home / ".config",
            "XDG_DATA_HOME": home / ".local/share",
            "XDG_STATE_HOME": home / ".local/state",
            "XDG_CACHE_HOME": home / ".cache",
        }
        seed_config_dir(xdg["XDG_CONFIG_HOME"] / "opencode", settings)
        environ["HOME"] = str(home)
        environ.update({name: str(path) for name, path in xdg.items()})
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
