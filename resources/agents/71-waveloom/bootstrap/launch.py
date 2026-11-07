"""Map ABB's selected OpenAI-compatible model onto Waveloom's native ACP server."""
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
PROVIDER_ENV = "ABB_AGENT_MODEL_PROVIDER"
WAVELOOM_BIN = "/opt/waveloom/bin/waveloom"
# Waveloom's llm.provider values with native request handling; any other
# selected provider is an OpenAI-compatible endpoint ("openai").
NATIVE_PROVIDERS = {"deepseek": "deepseek", "glm": "glm"}


def settings(base_url: str, model: str, provider: str) -> dict[str, object]:
    """Return a Waveloom settings.json without the credential.

    llm.api_key is left empty so Waveloom falls back to the LLM_API_KEY
    environment variable (docs/settings.en.md); the key is never written to disk.
    """
    return {
        "llm": {
            "provider": NATIVE_PROVIDERS.get(provider, "openai"),
            "model": model,
            "base_url": base_url,
            "api_key": "",
        },
    }


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Return the Waveloom ACP command, child environment and settings."""
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    provider = environ.get(PROVIDER_ENV, "").strip().lower()
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    if not base_url:
        raise ValueError(f"{BASE_URL_ENV} is required")
    if not model:
        raise ValueError(f"{MODEL_ENV} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")

    settings_path = home / "settings.json"
    settings_path.write_text(json.dumps(settings(base_url, model, provider), indent=2))
    child = {**environ, "HOME": str(home), "LLM_API_KEY": key}
    command = [
        WAVELOOM_BIN, "acp",
        "--settings", str(settings_path),
        "--session-dir", str(home / "acp-sessions"),
        "--model", model,
        # ACP mode always activates Waveloom's OS sandbox (bubblewrap); the
        # documented switch for already-isolated Docker/CI runs turns it off.
        # Waveloom's Guard (deny rules, high-risk and dangerous-path blocks)
        # still applies.
        "--no-sandbox",
    ]
    return command, child, settings(base_url, model, provider)


def main() -> int:
    try:
        # Disposable HOME: settings, ACP sessions and ~/.waveloom logs stay
        # writable by the runtime's unprivileged uid and per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-waveloom-home-"))
        command, environ, _ = prepare(dict(os.environ), home)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    # ABB prepares the Case workspace as a world-writable host directory and
    # removes it from the host after the run. Directories the agent creates
    # (e.g. Python's __pycache__) would otherwise be 0755 and owned by the
    # container uid, which the host cannot delete, and the Case is reported as
    # blocked. Keep created files as permissive as the prepared workspace.
    os.umask(0)
    os.execve(command[0], command, environ)
    return 1  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
