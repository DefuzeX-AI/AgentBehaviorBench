"""Map the shared OpenAI-compatible model onto OpenSoul's Gateway + ACP bridge.

OpenSoul exposes a headless ACP server (`opensoul acp`) that is a protocol
bridge: it speaks ACP over stdio and forwards each prompt to a locally running
OpenSoul Gateway over WebSocket. The Gateway owns the agent and its model; both
processes read the same `~/.opensoul/opensoul.json`. This launcher writes one
config that declares a custom DeepSeek provider from the shared
`ABB_AGENT_MODEL_*` variables, starts the Gateway in the background, waits for
its WebSocket port, then execs the ACP bridge in the foreground.

The API key is only ever exported to the child environment. The config file
references the environment variable by name and never stores the secret.
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from urllib.parse import urlsplit

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
PROVIDER_ENV = "ABB_AGENT_MODEL_PROVIDER"

# The config references this variable by name; the value is only ever exported
# to the child environment, never written to disk.
KEY_VARIABLE = "DEEPSEEK_API_KEY"

OPENSOUL_ROOT = Path("/opt/agent")
OPENSOUL_ENTRY = OPENSOUL_ROOT / "opensoul.mjs"
GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 18789
DEFAULT_SESSION = "agent:main:main"


def render_config(base_url: str, model: str) -> str:
    """Return the opensoul.json that binds the shared model route explicitly.

    DeepSeek is not one of OpenSoul's built-in providers, so it is declared as a
    custom OpenAI-completions provider. `apiKey` uses OpenSoul's `${VAR}` config
    substitution syntax: the config file stores only the variable name and
    OpenSoul resolves the secret from the environment at load time, so no secret
    is persisted. (A bare `DEEPSEEK_API_KEY` without `${}` is treated as a literal
    key string for custom providers, which is not what we want.)
    """
    config = {
        "models": {
            "providers": {
                "deepseek": {
                    "baseUrl": base_url,
                    "api": "openai-completions",
                    "apiKey": f"${{{KEY_VARIABLE}}}",
                    "models": [
                        {
                            "id": model,
                            "name": f"DeepSeek {model}",
                            "reasoning": False,
                            "input": ["text"],
                            "cost": {
                                "input": 0.27,
                                "output": 1.10,
                                "cacheRead": 0.07,
                                "cacheWrite": 0.27,
                            },
                            "contextWindow": 128000,
                            "maxTokens": 8192,
                        }
                    ],
                }
            }
        },
        "agents": {"defaults": {"model": {"primary": f"deepseek/{model}"}}},
        "gateway": {
            "mode": "local",
            # The container is headless (ACP stdio only). Leaving the Control UI
            # enabled would make the Gateway try to build its web assets at
            # startup, which is wasteful here and the build itself needs more
            # memory than the 1 GiB container provides.
            "controlUi": {"enabled": False},
        },
    }
    return json.dumps(config, indent=2)


def wait_for_port(host: str, port: int, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=1.0):
                return True
        except OSError:
            time.sleep(0.2)
    return False


def prepare(environ, home):
    """Validate the shared model inputs and return the two commands + child env."""
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

    # The shared config the Gateway and the ACP bridge both read.
    state_dir = home / ".opensoul"
    state_dir.mkdir(parents=True, exist_ok=True)
    config_path = state_dir / "opensoul.json"
    config_path.write_text(render_config(base_url, model), encoding="utf-8")
    config_path.chmod(0o600)

    # The Gateway defaults to token auth even on loopback. Both the Gateway and
    # the ACP bridge read the same OPENSOUL_GATEWAY_TOKEN from this environment,
    # so a per-run random token satisfies the auth requirement without becoming
    # a persistent secret.
    gateway_token = secrets.token_hex(16)

    child = dict(environ)
    child.update({
        KEY_VARIABLE: key,
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        # The messaging channels (Discord/Telegram/Matrix/...) would otherwise
        # dial outbound; the headless container only runs the agent + ACP.
        "OPENSOUL_SKIP_CHANNELS": "1",
        "OPENSOUL_GATEWAY_TOKEN": gateway_token,
        # The agent container is capped at 1 GiB, so Node sizes its V8 heap down
        # to ~512 MiB by default; the Gateway's startup allocations exceed that.
        # 768 MiB leaves headroom for the transient startup spike while keeping
        # the Gateway (~325 MiB steady state) and the ACP bridge inside the cap.
        "NODE_OPTIONS": "--max-old-space-size=768",
        "NODE_ENV": "production",
        "NO_COLOR": "1",
    })
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL",
                 "OTEL_SDK_DISABLED"):
        child.pop(name, None)

    gateway_cmd = [
        "node", str(OPENSOUL_ENTRY), "gateway",
        "--allow-unconfigured", "--port", str(GATEWAY_PORT), "--bind", "loopback",
    ]
    acp_cmd = [
        "node", str(OPENSOUL_ENTRY), "acp",
        "--url", f"ws://{GATEWAY_HOST}:{GATEWAY_PORT}",
        "--session", DEFAULT_SESSION,
    ]
    return gateway_cmd, acp_cmd, child, config_path


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="abb-opensoul-home-"))
    for sub in (".config", ".local/share", ".local/state", ".cache"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    try:
        environ = {**os.environ, "HOME": str(home)}
        gateway_cmd, acp_cmd, child, config_path = prepare(environ, home)

        log_path = home / "gateway.log"
        print(
            f"abb-opensoul: base_url={child[BASE_URL_ENV]} model={child[MODEL_ENV]} "
            f"config={config_path} gateway_log={log_path}",
            file=sys.stderr, flush=True,
        )

        # The Gateway must not touch stdio: stdout is the ACP protocol channel
        # once this process execs the bridge, so its logs go to a file.
        with open(log_path, "ab") as log:
            proc = subprocess.Popen(
                gateway_cmd,
                cwd=str(OPENSOUL_ROOT),
                env=child,
                stdout=log,
                stderr=subprocess.STDOUT,
            )

        if not wait_for_port(GATEWAY_HOST, GATEWAY_PORT, timeout=60.0):
            print("abb-opensoul: gateway did not listen in time", file=sys.stderr, flush=True)
            if proc.poll() is not None:
                print(f"abb-opensoul: gateway exited early (code={proc.returncode})",
                      file=sys.stderr, flush=True)
            try:
                tail = log_path.read_text(encoding="utf-8", errors="replace")[-4000:]
                print(f"abb-opensoul: gateway.log tail:\n{tail}", file=sys.stderr, flush=True)
            except OSError:
                pass
            proc.terminate()
            return 1

        # Replace this process with the ACP bridge; the Gateway stays as a child
        # in the same process group and is torn down with the container.
        os.execvpe(acp_cmd[0], acp_cmd, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr, flush=True)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
