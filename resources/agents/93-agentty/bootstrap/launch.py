"""Map ABB's selected OpenAI-compatible model onto agentty's native ACP server."""
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
AGENTTY_BIN = "/opt/agentty/bin/agentty"


def prepare(environ: dict[str, str], home: Path, start_relay=model_relay.start) -> tuple[list[str], dict[str, str]]:
    """Return the agentty ACP command and child environment.

    agentty talks to an OpenAI-compatible `--provider host[:port]` at
    /v1/chat/completions and lists /v1/models at startup, so it is pointed at
    the loopback model relay (see model_relay.py), which must not go through
    the runtime proxy. The key is read from OPENAI_API_KEY; agentty does not
    persist it.

    `--sandbox off`: agentty wraps commands in its in-process claybin sandbox
    (seccomp + landlock + cgroup2). In the runtime container every spawn failed
    with "claybin: spawn failed: child setup (errno 38)" and no command ran, so
    the unit disables the wrapper with agentty's documented switch; the Case
    container is the isolation boundary. File tools stay confined to the
    workspace (`--workspace`, default cwd).
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

    _, url = start_relay(base_url)
    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = {**environ, "HOME": str(home), "OPENAI_API_KEY": key,
             "NO_PROXY": no_proxy, "no_proxy": no_proxy}
    command = [AGENTTY_BIN, "acp", "--provider", urlsplit(url).netloc, "-m", model, "--sandbox", "off"]
    return command, child


def main() -> int:
    try:
        # Disposable HOME: ~/.agentty settings, threads and logs stay per Case
        # and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-agentty-home-"))
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
    # agentty runs as a child so the relay thread stays alive; it inherits the
    # ACP stdio directly.
    child = subprocess.Popen(command, env=environ)
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
