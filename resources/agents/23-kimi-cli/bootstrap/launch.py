"""Map an OpenAI-compatible GLM profile onto Kimi Code CLI's native ACP server."""
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
KIMI = "/opt/kimi/bin/kimi"

# Kimi's ACP `session/new` refuses to start unless a Kimi Code OAuth token file
# exists, even when the configured provider is not Kimi (upstream 1.50.0,
# kimi_cli/acp/server.py _check_token_usable). This placeholder only satisfies
# that local presence check: no managed Kimi provider or Moonshot service is
# configured, so nothing ever reads it to authenticate, and the empty
# refresh_token means the OAuth refresher never contacts Kimi's auth server.
PLACEHOLDER_TOKEN = {
    "access_token": "not-used-acp-gate-bypass",
    "refresh_token": "",
    "expires_at": 0,
    "scope": "",
    "token_type": "Bearer",
}

# FetchURL cannot be removed from the default ACP agent without an agent file
# (which `kimi acp` does not accept), and it would issue direct HTTP requests
# outside the admitted model route. A PreToolUse hook (exit code 2 = block)
# refuses it locally and returns the reason to the model as a tool error.
FETCH_BLOCK_HOOK = (
    "echo 'FetchURL is unavailable in this environment: network access is limited "
    "to the model endpoint.' >&2; exit 2"
)


def _toml_str(value: str) -> str:
    # JSON string escaping is valid TOML basic-string syntax for these values.
    return json.dumps(value)


def render_config(base_url: str, model: str) -> str:
    """Return Kimi's config.toml selecting the GLM model by default."""
    return "\n".join(
        [
            'default_model = "glm"',
            # GLM thinking output is not needed for the evaluated behaviour and
            # slows every step; keep the upstream default (off) explicit.
            "default_thinking = false",
            # Telemetry is sent to telemetry-logs.kimi.com, outside the model route.
            "telemetry = false",
            "",
            "[providers.zhipu]",
            'type = "openai_legacy"',
            f"base_url = {_toml_str(base_url)}",
            # The key comes from OPENAI_API_KEY in the environment, which Kimi's
            # openai_legacy provider prefers over this field; it is never written here.
            'api_key = ""',
            "",
            "[models.glm]",
            'provider = "zhipu"',
            f"model = {_toml_str(model)}",
            "max_context_size = 200000",
            "",
            "[[hooks]]",
            'event = "PreToolUse"',
            'matcher = "^FetchURL$"',
            f"command = {_toml_str(FETCH_BLOCK_HOOK)}",
            "timeout = 10",
            "",
        ]
    )


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], str]:
    """Return the Kimi ACP command, its environment and config text."""
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

    child = {
        **environ,
        # Kimi's openai_legacy provider reads these; the key never appears in
        # argv or on disk, where process listings and evidence could capture it.
        "OPENAI_API_KEY": key,
        "OPENAI_BASE_URL": base_url,
        # Belt and braces next to `telemetry = false` / no shell UI updater.
        "KIMI_DISABLE_TELEMETRY": "1",
        "KIMI_CLI_NO_AUTO_UPDATE": "1",
    }
    child.pop("KIMI_SHARE_DIR", None)
    return [KIMI, "acp"], child, render_config(base_url, model)


def hide_client_terminal(line: bytes) -> bytes:
    """Clear clientCapabilities.terminal in the ACP initialize request.

    When the client advertises terminals, Kimi replaces its Shell tool with one
    that sends the whole shell line as terminal/create `command` with no `args`
    (kimi_cli/acp/tools.py). ACP defines `command` as the executable, and ABB's
    client execs it literally, so every Shell call fails with "Internal error".
    Without the capability Kimi keeps its native Shell tool, which runs the same
    command through bash inside this container; tool calls are still reported
    as ACP tool_call updates. Every other message is forwarded byte for byte.
    """
    try:
        message = json.loads(line)
    except ValueError:
        return line
    if not isinstance(message, dict) or message.get("method") != "initialize":
        return line
    capabilities = (message.get("params") or {}).get("clientCapabilities")
    if not isinstance(capabilities, dict) or not capabilities.get("terminal"):
        return line
    capabilities["terminal"] = False
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def relay_stdin(child: subprocess.Popen) -> None:
    """Forward the client's newline-delimited JSON-RPC stream to Kimi."""
    try:
        for line in iter(sys.stdin.buffer.readline, b""):
            child.stdin.write(hide_client_terminal(line))
            child.stdin.flush()
    except (BrokenPipeError, OSError, ValueError):
        pass
    finally:
        try:
            child.stdin.close()
        except (BrokenPipeError, OSError):
            pass


def main() -> int:
    try:
        command, environ, config = prepare(dict(os.environ))
        # A disposable HOME keeps ~/.kimi (config, sessions, logs) writable by
        # whichever unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-kimi-home-"))
        share = home / ".kimi"
        (share / "credentials").mkdir(parents=True, mode=0o700)
        (share / "config.toml").write_text(config)
        token_file = share / "credentials/kimi-code.json"
        token_file.write_text(json.dumps(PLACEHOLDER_TOKEN))
        token_file.chmod(0o600)
        environ["HOME"] = str(home)
        # Kimi writes ACP to our stdout and logs to our stderr directly; only the
        # client-to-agent direction passes through this process (see above).
        child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(sig, lambda signum, _frame: child.send_signal(signum))
    threading.Thread(target=relay_stdin, args=(child,), daemon=True).start()
    code = child.wait()
    return code if code >= 0 else 128 - code


if __name__ == "__main__":
    raise SystemExit(main())
