"""Map ABB's selected OpenAI-compatible model onto Orca's native ACP mode."""
from __future__ import annotations

import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
ORCA_BIN = "/opt/orca/bin/orca"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Return the Orca ACP command and child environment.

    Orca's DeepSeek provider sends POST <base>/chat/completions, with the base
    URL from DEEPSEEK_BASE_URL and the key from ORCA_API_KEY (both documented
    on its CLI), so the credential is neither on the command line nor written
    to disk.

    ORCA_MODE=full-auto: in the default modes Orca runs shell commands only
    under an OS sandbox (bubblewrap) and otherwise removes the shell tool for
    the session. The runtime container does not let bubblewrap create its
    namespaces, so the unit selects full-auto, which Orca documents as the
    explicit trusted-host policy (docs/architecture/capability-kernel.md); the
    Case container is the isolation boundary.
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

    # Pricing refresh fetches models.dev, which the egress policy refuses.
    config_dir = home / ".orca"
    config_dir.mkdir()
    (config_dir / "config.toml").write_text("[pricing]\nrefresh = false\n")
    child = {**environ, "HOME": str(home), "ORCA_API_KEY": key, "DEEPSEEK_BASE_URL": base_url,
             "ORCA_MODE": "full-auto"}
    command = [ORCA_BIN, "--mode=acp", "--model", model]
    return command, child


def main() -> int:
    try:
        # Disposable HOME: ~/.orca config, sessions, memory and caches stay per
        # Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-orca-home-"))
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
