"""Map an OpenAI-compatible Codex profile onto Claude Code's Anthropic client."""
from __future__ import annotations

import os
from pathlib import Path
import sys
from urllib.parse import urlsplit, urlunsplit


KEY_ENV = "CODEX_API_KEY"
BASE_URL_ENV = "CODEX_API_BASE_URL"
MODEL_ENV = "CODEX_MODEL"


def prepare(unit: Path, environ: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return the bridge command and a Claude SDK environment without persisting secrets."""
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
    if not parsed.path.rstrip("/").endswith("/v1"):
        raise ValueError(f"{BASE_URL_ENV} must end in /v1")

    # Claude's SDK appends /v1/messages, while Codex stores the OpenAI-style
    # base including /v1. Remove that suffix so both resolve to the same route.
    parent_path = parsed.path.rstrip("/")[:-3].rstrip("/")
    anthropic_base = urlunsplit((parsed.scheme, parsed.netloc, parent_path, "", ""))
    child = {
        **environ,
        "ANTHROPIC_AUTH_TOKEN": key,
        "ANTHROPIC_API_KEY": "",
        "ANTHROPIC_BASE_URL": anthropic_base,
        "ANTHROPIC_MODEL": model,
        "ANTHROPIC_CUSTOM_MODEL_OPTION": model,
        "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC": "1",
        "DISABLE_AUTOUPDATER": "1",
        "NO_BROWSER": "1",
    }
    command = ["node", str(unit / "agent/dist/index.js")]
    return command, child


def main() -> int:
    try:
        command, environ = prepare(Path(__file__).resolve().parents[1], dict(os.environ))
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
