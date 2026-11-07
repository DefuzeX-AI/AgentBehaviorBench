"""Map ABB's selected OpenAI-compatible model onto Aster's native ACP server."""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import model_relay


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
ASTER_BIN = "/opt/aster/bin/aster"


def prepare(environ: dict[str, str], home: Path, relay_url: str) -> tuple[list[str], dict[str, str]]:
    """Return the Aster ACP command and child environment.

    Aster resolves its endpoint from ASTER_BASE_URL, ASTER_MODEL and
    ASTER_API_KEY, which outrank ~/.aster/aster.yaml, and sends
    POST <base>/chat/completions. ASTER_BASE_URL is the loopback model relay
    (see model_relay.py), which must not go through the runtime proxy. The
    credential stays in the environment, so it is neither on the command line
    nor written to disk.
    """
    key = environ.get(KEY_ENV, "").strip()
    model = environ.get(MODEL_ENV, "").strip()
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    if not model:
        raise ValueError(f"{MODEL_ENV} is required")

    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = {**environ, "HOME": str(home), "ASTER_API_KEY": key,
             "ASTER_BASE_URL": relay_url, "ASTER_MODEL": model,
             "NO_PROXY": no_proxy, "no_proxy": no_proxy}
    command = [ASTER_BIN, "acp", "--no-mcp"]
    return command, child


def validated_base_url(environ: dict[str, str]) -> str:
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    if not base_url:
        raise ValueError(f"{BASE_URL_ENV} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    return base_url


def main() -> int:
    try:
        # Disposable HOME: ~/.aster settings, sessions and caches stay per Case
        # and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-aster-home-"))
        _, relay_url = model_relay.start(validated_base_url(dict(os.environ)))
        command, environ = prepare(dict(os.environ), home, relay_url)
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
    # Aster runs as a child so the relay thread stays alive; it inherits the
    # ACP stdio directly.
    child = subprocess.Popen(command, env=environ)
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
