"""Map an OpenAI-compatible GLM profile onto Goose's native ACP server and relay its stdio."""
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
GOOSE_BIN = "/opt/goose/bin/goose"
PROVIDER_ID = "abb_glm"
# Context windows copied from upstream's bundled Z.AI provider definition
# (crates/goose-providers/src/declarative/definitions/zai.json at the pinned
# tag). Unknown models fall back to Goose's DEFAULT_CONTEXT_LIMIT.
CONTEXT_LIMITS = {
    "glm-5.1": 200_000,
    "glm-5": 204_800,
    "glm-5-turbo": 200_000,
    "glm-4.7": 204_800,
    "glm-4.6": 204_800,
    "glm-4.5": 131_072,
    "glm-4.5-air": 131_072,
}
DEFAULT_CONTEXT_LIMIT = 128_000


def provider_config(base_url: str, model: str) -> dict[str, object]:
    """Return a Goose custom-provider definition that never lists models remotely."""
    return {
        "name": PROVIDER_ID,
        "engine": "openai",
        "display_name": "GLM (ABB)",
        "description": "OpenAI-compatible GLM endpoint configured by ABB",
        # Goose resolves the credential from this environment variable at
        # request time; the key itself is never written into the file.
        "api_key_env": KEY_ENV,
        "base_url": base_url,
        # A static model list with an explicit context window keeps Goose from
        # calling GET <base>/models (session-init inventory refresh and the
        # context-window probe), which is outside the admitted model route.
        "models": [{"name": model, "context_limit": CONTEXT_LIMITS.get(model, DEFAULT_CONTEXT_LIMIT)}],
        "dynamic_models": False,
        "supports_streaming": True,
    }


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Return the Goose ACP command, environment and provider file without persisting secrets."""
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

    # Goose reads its config keys from upper-case environment variables, so no
    # config.yaml is needed. The OpenAI engine appends /chat/completions to the
    # base URL (the GLM URL has no /v1 suffix), which is exactly the admitted route.
    child = {
        **environ,
        KEY_ENV: key,
        "GOOSE_PROVIDER": PROVIDER_ID,
        "GOOSE_MODEL": model,
        # No desktop keyring in the container; without this Goose probes the
        # Secret Service over D-Bus before falling back to file storage.
        "GOOSE_DISABLE_KEYRING": "1",
        # Usage telemetry goes to PostHog (us.i.posthog.com), outside the
        # evaluated model route; the interceptor would reject it as egress.
        "GOOSE_TELEMETRY_OFF": "1",
        # After the first prompt Goose starts a background "short title" model
        # call; the one-shot worker closes ACP before it finishes and the
        # request is cut. The value must be a boolean literal ("1" is ignored).
        "GOOSE_DISABLE_SESSION_NAMING": "true",
    }
    return [GOOSE_BIN, "acp"], child, provider_config(base_url, model)


def adapt_terminal_request(line: bytes) -> bytes:
    """Run Goose's shell-string terminal commands through /bin/sh.

    Goose's ACP shell tool sends the whole command line as terminal/create
    ``command`` with no ``args`` (Zed runs it through the user's shell). ABB's
    client executes ``command`` directly as argv[0], so any command containing
    a space fails with ENOENT. Wrapping it keeps execution in ABB's terminal
    (same permission flow and evidence) with shell semantics.
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
    """Run Goose as a child and relay ACP stdio, adapting terminal/create requests."""
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
        command, environ, provider = prepare(dict(os.environ))
        # A disposable HOME keeps Goose's config, sessions database and request
        # logs writable by whichever unprivileged uid the runtime selects, and
        # isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-goose-home-"))
        environ["HOME"] = str(home)
        for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                         ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
            (home / sub).mkdir(parents=True, exist_ok=True)
            environ[var] = str(home / sub)
        providers_dir = home / ".config/goose/custom_providers"
        providers_dir.mkdir(parents=True)
        (providers_dir / f"{PROVIDER_ID}.json").write_text(json.dumps(provider, indent=2))
        return relay(command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
