"""Map ABB's selected OpenAI-compatible model onto code-assistant's ACP mode."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
CA_BIN = "/opt/code-assistant/bin/code-assistant"
PROVIDER_ID = "abb"
# Not in code-assistant's built-in catalog; without a limit it would assume a
# small default window and compact early.
CONTEXT_TOKEN_LIMIT = 128000


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Write the per-Case configuration and return the ACP command and environment.

    providers.json declares one `openai` (Chat Completions) provider whose
    api_key is the literal "${ABB_AGENT_MODEL_API_KEY}", which code-assistant
    expands when it loads the file, so the key is never written to disk; the
    client sends POST <base_url>/chat/completions. models.json names the
    selected model after its own id and points it at that provider.
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

    config_dir = home / ".config" / "code-assistant"
    config_dir.mkdir(parents=True)
    providers = {PROVIDER_ID: {"label": "ABB selected model", "provider": "openai",
                               "config": {"api_key": "${" + KEY_ENV + "}", "base_url": base_url}}}
    models = {model: {"provider": PROVIDER_ID, "id": model,
                      "context_token_limit": CONTEXT_TOKEN_LIMIT, "config": {}}}
    (config_dir / "providers.json").write_text(json.dumps(providers, indent=2))
    (config_dir / "models.json").write_text(json.dumps(models, indent=2))
    child = {**environ, "HOME": str(home)}
    command = [CA_BIN, "--config-dir", str(config_dir), "acp", "--model", model]
    return command, child


def adapt_terminal_request(line: bytes) -> bytes:
    """Run code-assistant's shell-string terminal commands through /bin/sh.

    code-assistant's execute_command sends the whole command line as
    terminal/create ``command`` with no ``args`` (as 17-goose does). ABB's
    client executes ``command`` directly as argv[0], so any command containing
    a space fails with ENOENT and code-assistant falls back to its own PTY.
    Wrapping it keeps execution in ABB's terminal (same permission flow and
    evidence) with shell semantics.
    """
    if b'"terminal/create"' not in line:
        return line
    try:
        message = json.loads(line)
    except ValueError:
        return line
    params = message.get("params") if isinstance(message, dict) else None
    if message.get("method") != "terminal/create" or not isinstance(params, dict):
        return line
    command = params.get("command")
    if not isinstance(command, str) or not command or params.get("args"):
        return line
    params["command"], params["args"] = "/bin/sh", ["-c", command]
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def relay(command: list[str], environ: dict[str, str]) -> int:
    """Run code-assistant as a child and relay ACP stdio, adapting terminal/create requests."""
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))

    def client_to_agent() -> None:
        try:
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
    out = sys.stdout.buffer
    try:
        for line in child.stdout:
            out.write(adapt_terminal_request(line))
            out.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


def main() -> int:
    try:
        # Disposable HOME: code-assistant's config, sessions and caches stay per
        # Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-code-assistant-home-"))
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
    return relay(command, environ)


if __name__ == "__main__":
    raise SystemExit(main())
