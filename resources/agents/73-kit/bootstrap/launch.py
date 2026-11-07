"""Map ABB's selected OpenAI-compatible model onto Kit's native ACP server."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
KIT_BIN = "/opt/kit/bin/kit"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Return the Kit ACP command and child environment.

    `--model openai/<model> --provider-url <base>` makes Kit call
    POST <base>/chat/completions (checked against a local stub). With a custom
    provider URL Kit does not read OPENAI_API_KEY; the credential is passed as
    KIT_PROVIDER_API_KEY (Kit's KIT_-prefixed form of --provider-api-key), so it
    is neither on the command line nor written to disk.
    """
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

    child = {**environ, "HOME": str(home), "KIT_PROVIDER_API_KEY": key}
    command = [KIT_BIN, "acp", "--model", f"openai/{model}", "--provider-url", base_url]
    return command, child


def main() -> int:
    try:
        # Disposable HOME: ~/.kit.yml lookup, session JSONL files and caches stay
        # per Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-kit-home-"))
        command, environ = prepare(dict(os.environ), home)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    # ABB prepares the Case workspace as a world-writable host directory and
    # removes it from the host after the run; directories the agent creates
    # (e.g. Python's __pycache__) would otherwise be 0755 and owned by the
    # container uid, which the host cannot delete. Keep them as permissive as
    # the prepared workspace.
    os.umask(0)
    os.execve(command[0], command, environ)
    return 1  # unreachable


if __name__ == "__main__":
    raise SystemExit(main())
