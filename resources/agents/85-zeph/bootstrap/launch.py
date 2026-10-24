"""Map ABB's selected OpenAI-compatible model onto Zeph's ACP server."""
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

import model_relay


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
ZEPH_BIN = "/opt/zeph/bin/zeph"
DEFAULT_CONFIG = Path("/opt/zeph/share/default.toml")
PROVIDER_NAME = "abb"
# The only [[llm.providers]] entry of the pinned default.toml (local Ollama).
DEFAULT_PROVIDER = """[[llm.providers]]
# Provider backend type: ollama, claude, openai, gemini, compatible, candle
type = "ollama"
model = "qwen3:8b"
embedding_model = "qwen3-embedding"
"""
DEFAULT_VAULT = 'backend = "age"'


def config_text(default: str, base_url: str, model: str) -> str:
    """Point the pinned default.toml at the selected endpoint.

    Zeph refuses a config that omits any section, so the unit starts from the
    upstream default.toml of the same commit and changes two things: the
    default local Ollama provider becomes one `compatible` (OpenAI Chat
    Completions) provider named `abb`, and the vault backend becomes `env`,
    so Zeph reads ZEPH_COMPATIBLE_ABB_API_KEY from the environment instead of
    an age-encrypted vault file.
    """
    if default.count(DEFAULT_PROVIDER) != 1 or default.count(DEFAULT_VAULT) != 1:
        raise ValueError("unexpected default.toml layout")
    provider = (f"[[llm.providers]]\nname = {json.dumps(PROVIDER_NAME)}\ntype = \"compatible\"\n"
                f"model = {json.dumps(model)}\nbase_url = {json.dumps(base_url)}\n")
    return default.replace(DEFAULT_PROVIDER, provider).replace(DEFAULT_VAULT, 'backend = "env"')


def prepare(environ: dict[str, str], home: Path, default: str,
            start_relay=model_relay.start) -> tuple[list[str], dict[str, str]]:
    """Write the per-Case config and return the Zeph ACP command and environment.

    The provider's base_url is the loopback model relay (see model_relay.py),
    which must not go through the runtime proxy.
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

    config_path = home / ".config" / "zeph" / "config.toml"
    config_path.parent.mkdir(parents=True)
    _, relay_url = start_relay(base_url)
    config_path.write_text(config_text(default, relay_url, model))
    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = {**environ, "HOME": str(home), "ZEPH_COMPATIBLE_ABB_API_KEY": key,
             "NO_PROXY": no_proxy, "no_proxy": no_proxy}
    command = [ZEPH_BIN, "--config", str(config_path), "--acp"]
    return command, child


def open_directories(root: Path) -> None:
    """Make the directories this uid created under `root` world-writable.

    Zeph keeps per-project state in <workspace>/.zeph (sessions and friends)
    and creates it 0755, so the host, which removes the Case workspace after
    the run, cannot delete entries in it; files need no change once their
    directory is writable.
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


# JSON-RPC code ACP defines for a missing resource.
RESOURCE_NOT_FOUND = -32002


def adapt_terminal_request(message: dict) -> bool:
    """Run a terminal/create whose ``command`` is a whole command line through /bin/sh.

    Zeph's bash tool lets the model fill ``command`` and ``args`` directly, and
    the model often puts the whole command line in ``command``: with no args
    (as 17-goose does), with its own arguments repeated in ``args``, or with
    ``args = ["-c"]``. ABB's client executes ``command`` directly as argv[0],
    so all of these failed with ENOENT. A ``command`` containing whitespace
    cannot name an executable, so it is run as ``/bin/sh -c <command>``; the
    stray ``args`` are dropped. Returns True if the message was changed.
    """
    params = message.get("params")
    if message.get("method") != "terminal/create" or not isinstance(params, dict):
        return False
    command = params.get("command")
    if not isinstance(command, str) or not any(ch.isspace() for ch in command.strip()):
        return False
    params["command"], params["args"] = "/bin/sh", ["-c", command]
    return True


def adapt_missing_file_error(message: dict) -> bool:
    """Report a read of a missing file as ACP ResourceNotFound; return True if changed.

    Before write_file Zeph reads the old content to build a diff and treats
    ResourceNotFound as "new file" (zeph-acp fs.rs ReadForDiff). ABB answers a
    read of a missing file with Internal error carrying "[Errno 2] No such
    file or directory", so every new-file write failed.
    """
    error = message.get("error")
    if not isinstance(error, dict) or error.get("code") == RESOURCE_NOT_FOUND:
        return False
    if "No such file or directory" not in json.dumps(error):
        return False
    message["error"] = {"code": RESOURCE_NOT_FOUND, "message": "Resource not found",
                        "data": error.get("data")}
    return True


def encode(message: dict) -> bytes:
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def relay(command: list[str], environ: dict[str, str], workspace: Path) -> int:
    """Run Zeph as a child and relay ACP stdio, adapting it to ABB's ACP client.

    terminal/create and missing-file read errors are adapted (see
    adapt_terminal_request and adapt_missing_file_error). Before a session/prompt reply (the end of a turn) is passed to the client,
    directories Zeph created in the workspace are opened (see open_directories):
    the runtime may stop the process without waiting for it once the last turn
    has ended.
    """
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))
    prompt_ids: set[object] = set()
    read_ids: set[object] = set()
    lock = threading.Lock()

    def client_to_agent() -> None:
        try:
            for line in sys.stdin.buffer:
                if b'"session/prompt"' in line or b'"error"' in line:
                    try:
                        message = json.loads(line)
                    except ValueError:
                        message = None
                    if isinstance(message, dict) and message.get("method") == "session/prompt":
                        with lock:
                            prompt_ids.add(message.get("id"))
                    elif isinstance(message, dict) and "error" in message:
                        with lock:
                            was_read = message.get("id") in read_ids
                            read_ids.discard(message.get("id"))
                        if was_read and adapt_missing_file_error(message):
                            line = encode(message)
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
            if b'"terminal/create"' in line or b'"fs/read_text_file"' in line:
                try:
                    message = json.loads(line)
                except ValueError:
                    message = None
                if isinstance(message, dict):
                    if message.get("method") == "fs/read_text_file":
                        with lock:
                            read_ids.add(message.get("id"))
                    elif adapt_terminal_request(message):
                        line = encode(message)
            elif b'"method"' not in line:
                try:
                    message = json.loads(line)
                except ValueError:
                    message = None
                if isinstance(message, dict) and "id" in message:
                    with lock:
                        ends_turn = message["id"] in prompt_ids
                        prompt_ids.discard(message["id"])
                    if ends_turn:
                        open_directories(workspace)
            out.write(line)
            out.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


def main() -> int:
    try:
        # Disposable HOME: Zeph's config, SQLite memory and caches stay per
        # Case and writable by the runtime's unprivileged uid.
        home = Path(tempfile.mkdtemp(prefix="abb-zeph-home-"))
        command, environ = prepare(dict(os.environ), home, DEFAULT_CONFIG.read_text())
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
