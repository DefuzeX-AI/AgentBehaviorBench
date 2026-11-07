"""Map ABB's selected OpenAI-compatible model onto Peri's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import struct
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
PERI_BIN = "/opt/peri/bin/peri"
PROVIDER_ID = "abb"


def settings(key: str, base_url: str, model: str) -> dict:
    """Return Peri settings with one `openai` (Chat Completions) provider.

    Every model tier and the active `opus` profile use the selected model, so
    sub-tasks that ask for a cheaper tier still go to the admitted route.
    """
    return {
        "config": {
            "active_alias": "opus",
            "providers": [{
                "id": PROVIDER_ID,
                "type": "openai",
                "apiKey": key,
                "baseUrl": base_url,
                "models": {"opus": model, "sonnet": model, "haiku": model, "fable": model},
            }],
            "profiles": {"opus": {"provider": PROVIDER_ID, "model": model}},
        }
    }


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], bytes]:
    """Return the Peri ACP command, its environment and the settings preamble.

    `peri acp --settings-stdin` reads a 4-byte big-endian length and a settings
    JSON object from stdin before ACP begins (peri-acp host/stdio
    read_bootstrap_settings), so the key reaches Peri without being written to
    disk or put on the command line. Peri sends POST <baseUrl>/chat/completions.
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

    document = json.dumps(settings(key, base_url, model)).encode()
    preamble = struct.pack(">I", len(document)) + document
    child = {k: v for k, v in environ.items() if k != KEY_ENV}
    child["HOME"] = str(home)
    command = [PERI_BIN, "acp", "--settings-stdin", "--cwd", os.getcwd()]
    return command, child, preamble


def relay(command: list[str], environ: dict[str, str], preamble: bytes) -> int:
    """Run Peri with the settings preamble, then pass ACP stdin through unchanged."""
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))

    def client_to_agent() -> None:
        try:
            child.stdin.write(preamble)
            child.stdin.flush()
            for line in sys.stdin.buffer:
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    threading.Thread(target=client_to_agent, daemon=True).start()
    return child.wait()


def main() -> int:
    try:
        # Disposable HOME: ~/.peri threads, workflows and caches stay per Case
        # and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-peri-home-"))
        command, environ, preamble = prepare(dict(os.environ), home)
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
    return relay(command, environ, preamble)


if __name__ == "__main__":
    raise SystemExit(main())
