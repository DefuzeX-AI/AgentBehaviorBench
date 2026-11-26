"""Map the selected OpenAI-compatible model profile onto Easy Code's native ACP server."""
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
# The published `easycode` bin. With `--acp` it serves ACP on stdio and moves its
# console logging to stderr, so stdout carries only JSON-RPC.
EASYCODE_BIN = (Path(__file__).resolve().parents[1]
                / "agent/node_modules/easycode-ai/bundle/easycode.js")
# Easy Code addresses a custom model as "custom:<displayName>".
MODEL_NAME = "abb"
# Variables that would select another server, auth type, settings or model file,
# host integration or provider credential if inherited from the container environment.
DROPPED_ENV = (
    "DEEPV_DEFAULT_AUTH_TYPE", "DEEPX_WEB_URL", "EASYCODE_CUSTOM_MODELS_FILE",
    "EASYCODE_USER_SETTINGS_FILE", "EASYCODE_HOST_SESSION_ID", "EASYCODE_DESKTOP_MANAGED",
    "EASYCODE_SHELL_MANAGED", "EASYCODE_KNOWLEDGE_SESSION", "GEMINI_CLI_SYSTEM_SETTINGS_PATH",
    "GEMINI_SANDBOX", "GOOGLE_APPLICATION_CREDENTIALS", "GOOGLE_CLOUD_PROJECT",
    "GOOGLE_CLOUD_LOCATION", "GOOGLE_CLOUD_QUOTA_PROJECT", "DEEPV_CODE_DEBUG",
)


def selection(environ: dict[str, str]) -> tuple[str, str, str]:
    """Return the validated key, base URL and model selected by the runtime."""
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
    return key, base_url, model


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Return the Easy Code ACP command and its environment."""
    selection(environ)
    # Easy Code reads the key from custom-models.json, so it is not passed on.
    child = {k: v for k, v in environ.items() if k not in DROPPED_ENV and k != KEY_ENV}
    child.update({
        "HOME": str(home),
        # The npm update notifier of any npm child process would contact the registry.
        "npm_config_update_notifier": "false",
        "NO_UPDATE_NOTIFIER": "1",
    })
    return ["node", str(EASYCODE_BIN), "--acp"], child


def custom_model(environ: dict[str, str]) -> dict[str, str]:
    """Return the single custom model entry for the selected provider."""
    key, base_url, model = selection(environ)
    # The "openai" custom provider posts to <baseUrl>/chat/completions, which is the
    # admitted shared route. A selected custom model is called directly, never
    # through Easy Code's own server, so no Easy Code account is involved.
    return {"displayName": MODEL_NAME, "provider": "openai", "baseUrl": base_url,
            "apiKey": key, "modelId": model}


def seed_home(home: Path, entry: dict[str, str]) -> None:
    """Write Easy Code's user settings and its single custom model."""
    user = home / ".easycode-user"
    user.mkdir(mode=0o700)
    # Without a preferred custom model, a session would start on "auto", which is
    # served only through Easy Code's own (unadmitted) server.
    (user / "settings.json").write_text(
        json.dumps({"preferredModel": f"custom:{MODEL_NAME}"}, indent=2), encoding="utf-8")
    # custom-models.json is the only place Easy Code reads a custom model's key; it has
    # no environment reference. Keep it owner-only in the disposable HOME.
    fd = os.open(user / "custom-models.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        json.dump({"models": [entry]}, stream, indent=2)


def main() -> int:
    try:
        # A disposable HOME keeps Easy Code's settings, sessions, checkpoints and logs
        # writable by whichever unprivileged uid the runtime selects, and isolates
        # Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-easycode-home-"))
        command, environ = prepare(dict(os.environ), home)
        seed_home(home, custom_model(dict(os.environ)))
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    sys.stdout.flush()
    sys.stderr.flush()
    # stdin/stdout are the ACP stdio channel; Easy Code takes them over directly.
    os.execvpe(command[0], command, environ)
    return 1  # pragma: no cover - execvpe does not return


if __name__ == "__main__":
    raise SystemExit(main())
