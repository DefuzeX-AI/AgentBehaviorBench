"""Map ABB's selected OpenAI-compatible model onto ggcode's native ACP server."""
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
GGCODE_BIN = "/opt/ggcode/bin/ggcode"
VENDOR = "abb"
ENDPOINT = "default"


def config(base_url: str, model: str) -> dict:
    """Return a ggcode.yaml (as JSON, a YAML subset) with one OpenAI-protocol endpoint.

    ggcode expands `${VAR}` in api_key when it loads the file, so the credential
    stays in the environment and is never written to disk.
    """
    return {
        "vendor": VENDOR,
        "endpoint": ENDPOINT,
        "model": model,
        "vendors": {
            VENDOR: {
                "display_name": "ABB selected model",
                "api_key": "${" + KEY_ENV + "}",
                "endpoints": {
                    ENDPOINT: {
                        "protocol": "openai",
                        "base_url": base_url,
                        "default_model": model,
                        "selected_model": model,
                        "models": [model],
                    }
                },
            }
        },
    }


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Write the per-Case config and return the ggcode ACP command and environment."""
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

    config_path = home / ".ggcode" / "ggcode.yaml"
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps(config(base_url, model), indent=2))
    child = {**environ, "HOME": str(home)}
    command = [GGCODE_BIN, "--config", str(config_path), "acp"]
    return command, child


class PromptCompletion:
    """Turn ggcode's early session/prompt reply into a standard end-of-turn reply.

    ggcode answers session/prompt at once with `{"stopReason": ""}` and reports
    the end of the turn later with a non-standard `session/prompt_complete`
    notification (internal/acp/handler.go handleSessionPrompt). An ACP client
    takes the first reply as the end of the turn. The relay holds that reply and
    answers the request when the matching prompt_complete arrives; error replies
    pass through unchanged.
    """

    def __init__(self, on_turn_end=lambda: None) -> None:
        self._on_turn_end = on_turn_end
        self._lock = threading.Lock()
        self._by_id: dict[object, str] = {}
        self._held: dict[str, object] = {}
        # A turn that fails at once can complete before its early reply.
        self._early: dict[str, str] = {}

    def from_client(self, line: bytes) -> None:
        if b'"session/prompt"' not in line:
            return
        try:
            message = json.loads(line)
        except ValueError:
            return
        if message.get("method") == "session/prompt" and "id" in message:
            with self._lock:
                self._by_id[message["id"]] = (message.get("params") or {}).get("sessionId", "")

    def from_agent(self, line: bytes) -> bytes | None:
        """Return the line to forward, or None to drop it."""
        try:
            message = json.loads(line)
        except ValueError:
            return line
        if not isinstance(message, dict):
            return line
        if message.get("method") == "session/prompt_complete":
            params = message.get("params") or {}
            session_id = params.get("sessionId", "")
            stop = (params.get("response") or {}).get("stopReason") or "end_turn"
            with self._lock:
                request_id = self._held.pop(session_id, None)
                if request_id is None:
                    if session_id in self._by_id.values():
                        self._early[session_id] = stop
                    return None
            self._on_turn_end()
            return _stop_reply(request_id, stop)
        if "id" in message and "method" not in message:
            with self._lock:
                session_id = self._by_id.pop(message["id"], None)
                if session_id is not None and "result" in message:
                    stop = self._early.pop(session_id, None)
                    if stop is not None:
                        self._on_turn_end()
                        return _stop_reply(message["id"], stop)
                    self._held[session_id] = message["id"]
                    return None
        return line


def _stop_reply(request_id: object, stop: str) -> bytes:
    reply = {"jsonrpc": "2.0", "id": request_id, "result": {"stopReason": stop}}
    return json.dumps(reply, separators=(",", ":")).encode() + b"\n"


def relay(command: list[str], environ: dict[str, str], workspace: Path) -> int:
    """Run ggcode as a child and relay ACP stdio, completing prompts on prompt_complete.

    Before each turn is reported complete, directories ggcode created in the
    workspace are opened (see open_directories): the runtime may stop the
    process without waiting for it once the last turn has ended.
    """
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))
    prompts = PromptCompletion(lambda: open_directories(workspace))

    def client_to_agent() -> None:
        try:
            for line in sys.stdin.buffer:
                prompts.from_client(line)
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
            forwarded = prompts.from_agent(line)
            if forwarded is not None:
                out.write(forwarded)
                out.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


def open_directories(root: Path) -> None:
    """Make the directories this uid created under `root` world-writable.

    ggcode keeps project state in <workspace>/.ggcode (memory, trajectory
    learnings, perf baseline) and creates those directories with an explicit
    0755, which the umask cannot widen. The host removes the Case workspace
    after the run and cannot delete entries in a 0755 directory owned by the
    container uid; files need no change once their directory is writable.
    """
    uid = os.getuid()
    for current, dirs, _files in os.walk(root):
        for name in dirs:
            path = Path(current, name)
            try:
                if not path.is_symlink() and path.stat().st_uid == uid:
                    path.chmod(0o777)
            except OSError:
                pass


def main() -> int:
    try:
        # Disposable HOME: ~/.ggcode config, ACP sessions and caches stay per
        # Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-ggcode-home-"))
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
    workspace = Path.cwd()
    try:
        return relay(command, environ, workspace)
    finally:
        open_directories(workspace)


if __name__ == "__main__":
    raise SystemExit(main())
