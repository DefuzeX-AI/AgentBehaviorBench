"""Map an OpenAI-compatible GLM profile onto Open Interpreter's native ACP server."""
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


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
INTERPRETER_BIN = "/opt/open-interpreter/bin/interpreter"
PROVIDER_ID = "abb_glm"
# Open Interpreter installs its apply_patch helper aliases under
# INTERPRETER_HOME but refuses to do so below the system temp dir, so the
# per-Case home lives in this image directory (mode 1777) instead of /tmp.
STATE_ROOT = "/var/lib/abb-open-interpreter"
# Context windows for GLM models (Zhipu/Z.AI published limits). Unknown models
# keep Open Interpreter's own default.
CONTEXT_LIMITS = {
    "glm-5.1": 200_000,
    "glm-5": 204_800,
    "glm-5-turbo": 200_000,
    "glm-4.7": 204_800,
    "glm-4.6": 204_800,
}


def toml_string(value: str) -> str:
    """Return a TOML basic string (JSON escaping is a valid subset)."""
    return json.dumps(value)


def config_toml(base_url: str, model: str) -> str:
    """Return config.toml selecting a Chat Completions provider; the key stays in the environment."""
    lines = [
        f"model_provider = {toml_string(PROVIDER_ID)}",
        f"model = {toml_string(model)}",
        # Web search is a hosted tool outside the admitted model route.
        'web_search = "disabled"',
        # Managed standalone update checks call GitHub/openinterpreter.com.
        "check_for_update_on_startup = false",
        # Debian's /etc/profile resets PATH for login shells, which drops the
        # per-session apply_patch helper directory Open Interpreter prepends
        # to PATH; shell tools therefore run as non-login `bash -c`.
        "allow_login_shell = false",
    ]
    if model in CONTEXT_LIMITS:
        lines.append(f"model_context_window = {CONTEXT_LIMITS[model]}")
    lines += [
        "",
        # Stable-on features that call hosted OpenAI/ChatGPT services at session
        # start (curated plugin sync from chatgpt.com / api.github.com / git,
        # featured plugins, app connectors) or offer hosted tools that are not
        # provisioned here. The interceptor rejects those calls as egress.
        "[features]",
        "plugins = false",
        "remote_plugin = false",
        "plugin_sharing = false",
        "apps = false",
        "tool_suggest = false",
        "browser_use = false",
        "computer_use = false",
        "image_generation = false",
        "in_app_updates = false",
        "",
        "[analytics]",
        "enabled = false",
        "",
        "[feedback]",
        "enabled = false",
        "",
        f"[model_providers.{PROVIDER_ID}]",
        'name = "GLM (ABB)"',
        f"base_url = {toml_string(base_url)}",
        # Open Interpreter reads the credential from this variable at request
        # time; the key itself is never written into the file.
        f"env_key = {toml_string(KEY_ENV)}",
        # The GLM coding endpoint is OpenAI Chat Completions compatible; the
        # chat wire appends /chat/completions, which is the admitted route.
        'wire_api = "chat"',
        "",
    ]
    return "\n".join(lines)


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], str]:
    """Return the ACP command, child environment and config text without persisting secrets."""
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
    child = {**environ, KEY_ENV: key}
    return [INTERPRETER_BIN, "acp"], child, config_toml(base_url, model)


class ChunkDeduplicator:
    """Drop the completed-item replay of an already streamed agent message.

    The pinned ACP server (codex-rs/acp-server/src/lib.rs, handle_notification)
    streams every AgentMessageDelta as an ``agent_message_chunk`` and then, on
    ItemCompleted, sends the whole AgentMessage text again as one more
    ``agent_message_chunk``. ACP clients concatenate chunks, so every reply
    would appear twice. The same happens for reasoning (``agent_thought_chunk``,
    whose replay joins summary/content parts with newlines). A chunk whose text
    equals everything streamed since the previous replay is that replay and is
    dropped; nothing else is changed.
    """

    KINDS = ("agent_message_chunk", "agent_thought_chunk")

    def __init__(self) -> None:
        self.streamed = {kind: "" for kind in self.KINDS}

    @staticmethod
    def _normalized(text: str) -> str:
        return "".join(text.split())

    def reset(self) -> None:
        """Forget streamed text at a boundary where no replay can still be pending."""
        for kind in self.KINDS:
            self.streamed[kind] = ""

    def filter(self, line: bytes) -> bytes | None:
        if b'"session/update"' not in line:
            return line
        try:
            message = json.loads(line)
            update = message["params"]["update"]
            kind = update.get("sessionUpdate")
            content = update.get("content") or {}
        except (ValueError, KeyError, TypeError, AttributeError):
            return line
        if kind not in self.KINDS:
            # A tool call or plan starts a new item; the previous message item
            # (and its replay, if any) has completed before it.
            self.reset()
            return line
        if content.get("type") != "text":
            return line
        text = content.get("text")
        if not isinstance(text, str):
            return line
        streamed = self.streamed[kind]
        if streamed and (text == streamed or (
                kind == "agent_thought_chunk" and self._normalized(text) == self._normalized(streamed))):
            self.streamed[kind] = ""
            return None
        self.streamed[kind] = streamed + text
        return line


class SessionModeSelector:
    """Switch every new ACP session to upstream's ``full-access`` mode before the client uses it.

    ``interpreter acp`` starts each session in ``workspace-write`` mode, whose
    commands and patches run inside Open Interpreter's bubblewrap sandbox.
    ABB's container policy (``--cap-drop=ALL``, ``no-new-privileges``) does not
    allow unprivileged user namespaces, so bubblewrap cannot start and every
    command or file change fails before execution; the legacy Landlock backend
    rejects the same permission profile. The container is the isolation
    boundary here, so the launcher selects the mode upstream exposes for that
    case: it holds the ``session/new`` response, sends ``session/set_mode``
    (``full-access``) to the agent, swallows that reply and then releases the
    held response with ``currentModeId`` updated. Nothing else is changed.
    """

    MODE_ID = "full-access"

    def __init__(self, write_to_agent) -> None:
        self.write_to_agent = write_to_agent
        self.lock = threading.Lock()
        self.new_session_ids: set[object] = set()
        self.pending: dict[str, dict] = {}
        self.counter = 0

    def from_client(self, line: bytes) -> None:
        if b'"session/new"' in line:
            try:
                message = json.loads(line)
            except ValueError:
                message = None
            if isinstance(message, dict) and message.get("method") == "session/new" and "id" in message:
                with self.lock:
                    self.new_session_ids.add(json.dumps(message["id"]))

    def from_agent(self, message: dict) -> list[dict] | None:
        """Return the messages to forward to the client, or None to forward unchanged."""
        if "method" in message or "id" not in message:
            return None
        key = json.dumps(message["id"])
        with self.lock:
            if key in self.pending:
                held = self.pending.pop(key)
                if "error" in message:
                    detail = message["error"].get("message", "unknown error")
                    return [{"jsonrpc": "2.0", "id": held["id"],
                             "error": {"code": -32603, "message": f"session/set_mode {self.MODE_ID} failed: {detail}"}}]
                modes = (held.get("result") or {}).get("modes")
                if isinstance(modes, dict):
                    modes["currentModeId"] = self.MODE_ID
                return [held]
            if key not in self.new_session_ids:
                return None
            self.new_session_ids.discard(key)
            session_id = (message.get("result") or {}).get("sessionId")
            if not session_id:
                return None
            self.counter += 1
            request_id = f"abb-launch-set-mode-{self.counter}"
            self.pending[json.dumps(request_id)] = message
        self.write_to_agent(json.dumps({
            "jsonrpc": "2.0", "id": request_id, "method": "session/set_mode",
            "params": {"sessionId": session_id, "modeId": self.MODE_ID},
        }, separators=(",", ":")).encode() + b"\n")
        return []


def relay(command: list[str], environ: dict[str, str]) -> int:
    """Run the ACP server as a child and relay stdio with the two adaptations above."""
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))
    stdin_lock = threading.Lock()

    def write_to_agent(data: bytes) -> None:
        with stdin_lock:
            child.stdin.write(data)
            child.stdin.flush()

    modes = SessionModeSelector(write_to_agent)
    dedup = ChunkDeduplicator()

    def client_to_agent() -> None:
        try:
            for line in sys.stdin.buffer:
                modes.from_client(line)
                if b'"session/prompt"' in line:
                    # Not every final message is replayed (the turn can end
                    # first), so each prompt starts with an empty buffer.
                    dedup.reset()
                write_to_agent(line)
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                with stdin_lock:
                    child.stdin.close()
            except OSError:
                pass

    threading.Thread(target=client_to_agent, daemon=True).start()
    out = sys.stdout.buffer
    try:
        for line in child.stdout:
            forward: list[bytes] = [line]
            if b'"id"' in line and b'"method"' not in line[:200]:
                try:
                    message = json.loads(line)
                except ValueError:
                    message = None
                if isinstance(message, dict):
                    replaced = modes.from_agent(message)
                    if replaced is not None:
                        forward = [json.dumps(m, separators=(",", ":")).encode() + b"\n" for m in replaced]
            for item in forward:
                kept = dedup.filter(item)
                if kept is not None:
                    out.write(kept)
                    out.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


def main() -> int:
    try:
        command, environ, config = prepare(dict(os.environ))
        # A disposable HOME/INTERPRETER_HOME keeps config, session rollouts,
        # the state database and logs writable by whichever unprivileged uid
        # the runtime selects, and isolates Cases from each other.
        root = STATE_ROOT if os.access(STATE_ROOT, os.W_OK) else None
        home = Path(tempfile.mkdtemp(prefix="abb-oi-home-", dir=root))
        oi_home = home / ".openinterpreter"
        oi_home.mkdir()
        (oi_home / "config.toml").write_text(config)
        environ["HOME"] = str(home)
        environ["INTERPRETER_HOME"] = str(oi_home)
        environ["CODEX_HOME"] = str(oi_home)
        for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                         ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
            (home / sub).mkdir(parents=True, exist_ok=True)
            environ[var] = str(home / sub)
        return relay(command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
