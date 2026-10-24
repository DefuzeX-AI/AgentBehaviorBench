"""Map ABB's selected OpenAI-compatible model onto Orca's native ACP mode."""
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
ORCA_BIN = "/opt/orca/bin/orca"

# Orca's ACP extension for its ask_user_question tool (src/acp/agent.rs).
INTERACTION_META_KEY = "orca.dev/interactionCapabilities"
USER_INPUT_METHOD = "_orca.dev/session/request_user_input"
NO_USER_REPLY = ("No user is available to answer questions in this session. "
                 "Proceed with reasonable assumptions and state them in your answer.")


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


class UserInputRelay:
    """Answer Orca's ask_user_question requests for a non-interactive ACP client.

    Orca always offers ask_user_question over ACP. When the client has not
    declared the `userInput` interaction capability, the question is cancelled
    and Orca fails the whole prompt (Internal error). The relay declares the
    capability on initialize and answers each user-input request with a `chat`
    outcome saying no user is available, which Orca returns to the model as an
    ordinary tool result ({"answers": {}, "chat": ...}).
    """

    def from_client(self, line: bytes) -> bytes:
        """Return the line to send to Orca."""
        if b'"initialize"' not in line:
            return line
        try:
            message = json.loads(line)
        except ValueError:
            return line
        if not isinstance(message, dict) or message.get("method") != "initialize":
            return line
        params = message.setdefault("params", {})
        capabilities = params.setdefault("clientCapabilities", {})
        meta = capabilities.get("_meta") or {}
        meta[INTERACTION_META_KEY] = {"version": 1, "userInput": True, "mcpElicitation": False}
        capabilities["_meta"] = meta
        return json.dumps(message, separators=(",", ":")).encode() + b"\n"

    def from_agent(self, line: bytes) -> tuple[bytes | None, bytes | None]:
        """Return (line for the client, reply for Orca)."""
        if USER_INPUT_METHOD.encode() not in line:
            return line, None
        try:
            message = json.loads(line)
        except ValueError:
            return line, None
        if not isinstance(message, dict) or message.get("method") != USER_INPUT_METHOD or "id" not in message:
            return line, None
        params = message.get("params") or {}
        result = {
            "version": params.get("version", 1),
            "sessionId": params.get("sessionId"),
            "interactionId": params.get("interactionId"),
            "response": {"outcome": "chat", "value": NO_USER_REPLY},
        }
        reply = {"jsonrpc": "2.0", "id": message["id"], "result": result}
        return None, json.dumps(reply, separators=(",", ":")).encode() + b"\n"


def relay(command: list[str], environ: dict[str, str]) -> int:
    """Run Orca as a child and relay ACP stdio through UserInputRelay."""
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda *_: child.terminate())
    adapter = UserInputRelay()
    to_agent = threading.Lock()

    def send_agent(data: bytes) -> None:
        with to_agent:
            child.stdin.write(data)
            child.stdin.flush()

    def client_to_agent() -> None:
        try:
            for line in iter(sys.stdin.buffer.readline, b""):
                send_agent(adapter.from_client(line))
        except (BrokenPipeError, ValueError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    threading.Thread(target=client_to_agent, daemon=True).start()
    out = sys.stdout.buffer
    try:
        for line in iter(child.stdout.readline, b""):
            forward, reply = adapter.from_agent(line)
            if reply is not None:
                send_agent(reply)
            if forward is not None:
                out.write(forward)
                out.flush()
    except (BrokenPipeError, ValueError):
        child.terminate()
    return child.wait()


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
    return relay(command, environ)


if __name__ == "__main__":
    raise SystemExit(main())
