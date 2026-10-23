"""Map the selected OpenAI-compatible model profile onto Mistral Vibe's native ACP server."""
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
VIBE_ACP = "/opt/vibe/bin/vibe-acp"


def _toml_str(value: str) -> str:
    # JSON string escaping is valid TOML basic-string syntax for these values.
    return json.dumps(value)


def render_config(base_url: str, model: str) -> str:
    """Return Vibe's config.toml selecting the configured model by default."""
    return "\n".join(
        [
            'active_model = "abb"',
            # Telemetry (and Sentry, which follows it) posts to Mistral services.
            "enable_telemetry = false",
            # Update checks and auto-update query the package index.
            "enable_update_checks = false",
            "enable_auto_update = false",
            # The greeting is fetched from Mistral; notifications need a desktop.
            "show_greeting = false",
            "enable_notifications = false",
            "",
            # GrowthBook experiments are fetched from experiments.mistral.services.
            "[experiments]",
            "enable = false",
            "",
            "[[providers]]",
            'name = "abb"',
            f"api_base = {_toml_str(base_url)}",
            # Vibe reads the key from this variable; it is never written here.
            f"api_key_env_var = {_toml_str(KEY_ENV)}",
            'api_style = "openai"',
            'backend = "generic"',
            "",
            "[[models]]",
            f"name = {_toml_str(model)}",
            'provider = "abb"',
            'alias = "abb"',
            "",
        ]
    )


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], str]:
    """Return the Vibe ACP command, its environment and config text."""
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

    child = dict(environ)
    # A Mistral key in the environment would make the default Mistral provider usable.
    child.pop("MISTRAL_API_KEY", None)
    return [VIBE_ACP], child, render_config(base_url, model)


def main() -> int:
    try:
        command, environ, config = prepare(dict(os.environ))
        # A disposable VIBE_HOME keeps config, sessions and logs writable by
        # whichever unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-vibe-home-"))
        (home / "config.toml").write_text(config)
        environ["VIBE_HOME"] = str(home)
        os.execve(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
