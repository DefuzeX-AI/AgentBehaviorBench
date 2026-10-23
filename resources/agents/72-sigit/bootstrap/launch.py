"""Map the selected OpenAI-compatible model profile onto siGit Code's native ACP server."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
SIGIT = "/opt/sigit/bin/sigit"


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return the siGit Code ACP command and its environment without persisting secrets."""
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

    # A disposable HOME keeps ~/.config/sigit (providers.toml, sessions, logs)
    # writable by whichever unprivileged uid the runtime selects, and isolates
    # Cases from each other. The credential stays in the environment, never on
    # disk, where process listings and evidence could capture it.
    home = Path(tempfile.mkdtemp(prefix="abb-sigit-home-"))
    config_dir = home / ".config" / "sigit"
    config_dir.mkdir(parents=True, exist_ok=True)

    child = {
        **environ,
        # siGit Code reads its explicit provider override from these
        # OpenAI-compatible variables. The OpenAI backend appends
        # /chat/completions to the base URL, matching the admitted model route.
        "OPENAI_API_KEY": key,
        "OPENAI_BASE_URL": base_url,
        "SIGIT_MODEL": model,
        # The official siGit MCP server needs a signed-in session and would be
        # undeclared egress; disable it so only the model route is used.
        "SIGIT_MCP_OFFICIAL": "off",
        # On-device telemetry is compiled out in release builds, but keep it
        # off explicitly in case the image runs a build with it enabled.
        "ONDE_DISABLE_PULSE": "1",
        "HOME": str(home),
        "SIGIT_CONFIG_DIR": str(config_dir),
    }
    return [SIGIT, "--acp"], child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
