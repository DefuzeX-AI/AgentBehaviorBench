"""Start a private OpenClaw Gateway for one Case, then serve its ACP bridge on stdio."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import secrets
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
TOKEN_ENV = "OPENCLAW_GATEWAY_TOKEN"
OPENCLAW = Path(__file__).resolve().parents[1] / "agent/node_modules/.bin/openclaw"
# Fixed because network/rules.toml admits exactly this loopback port: the runtime
# redirects all non-root TCP, loopback included, through the interceptor.
GATEWAY_PORT = 18799
READY_TIMEOUT_SEC = 150
STOP_TIMEOUT_SEC = 10
ANSI = re.compile(r"\x1b\[[0-9;]*[A-Za-z]")
READY = re.compile(r"\[gateway\]\s+ready\s*$", re.MULTILINE)


def validate(environ: dict[str, str]) -> tuple[str, str, str]:
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
    return key, base_url, model


def gateway_config(base_url: str, model: str, port: int, workdir: str) -> dict:
    """OpenClaw config; ${VAR} references are expanded by OpenClaw from its env."""
    return {
        "gateway": {
            "mode": "local",
            "port": port,
            "bind": "loopback",
            "auth": {"mode": "token", "token": "${" + TOKEN_ENV + "}"},
        },
        "agents": {
            "defaults": {
                "model": {"primary": f"glm/{model}"},
                # Coding tools run in the ABB Case workspace; OpenClaw's own
                # managed workspace (memory, persona files) stays in HOME.
                "cwd": workdir,
                # A fresh workspace otherwise gets BOOTSTRAP.md, a first-run
                # "birth sequence" persona ritual unrelated to the Case.
                "skipBootstrap": True,
                # Recurring heartbeat turns are extra model calls with no Case.
                "heartbeat": {"every": "0m"},
            }
        },
        "models": {
            # The Gateway otherwise fetches catalog.openclaw.ai at startup.
            "catalogRefresh": {"enabled": False},
            "mode": "merge",
            "providers": {
                "glm": {
                    "baseUrl": base_url,
                    "apiKey": "${" + KEY_ENV + "}",
                    "api": "openai-completions",
                    "models": [
                        {"id": model, "name": model, "contextWindow": 128000, "maxTokens": 8192}
                    ],
                }
            },
        },
        # Update checks and telemetry would be egress outside the model route.
        "update": {"checkOnStart": False, "auto": {"enabled": False}},
        "telemetry": {"enabled": False},
    }


def redact(text: str) -> str:
    for name in (KEY_ENV, TOKEN_ENV):
        value = os.environ.get(name) or ""
        if value:
            text = text.replace(value, "[REDACTED]")
    return text


def stop(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(STOP_TIMEOUT_SEC)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(STOP_TIMEOUT_SEC)


def wait_ready(gateway: subprocess.Popen, log_path: Path) -> None:
    deadline = time.monotonic() + READY_TIMEOUT_SEC
    while time.monotonic() < deadline:
        text = ANSI.sub("", log_path.read_text(errors="replace")) if log_path.exists() else ""
        if READY.search(text):
            return
        if gateway.poll() is not None:
            raise RuntimeError(f"OpenClaw Gateway exited with {gateway.returncode}:\n{text[-4000:]}")
        time.sleep(0.25)
    text = ANSI.sub("", log_path.read_text(errors="replace")) if log_path.exists() else ""
    raise RuntimeError(f"OpenClaw Gateway not ready after {READY_TIMEOUT_SEC}s:\n{text[-4000:]}")


def main() -> int:
    gateway = bridge = None
    try:
        _, base_url, model = validate(dict(os.environ))
        # A disposable HOME keeps OpenClaw's config, state and sessions writable
        # by whichever unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-openclaw-home-"))
        state = home / ".openclaw"
        state.mkdir(mode=0o700)
        port = GATEWAY_PORT
        config = gateway_config(base_url, model, port, os.getcwd())
        (state / "openclaw.json").write_text(json.dumps(config, indent=2))
        # A fresh Gateway token per Case. The bridge reads it from a 0600 file
        # so it never appears in argv; the Gateway expands it from env.
        token = secrets.token_hex(32)
        os.environ[TOKEN_ENV] = token
        token_file = state / "gateway.token"
        token_file.touch(mode=0o600)
        token_file.write_text(token)

        base = dict(os.environ)
        base.pop(TOKEN_ENV, None)
        base.pop(KEY_ENV, None)
        base.update({
            "HOME": str(home),
            # mDNS advertisement is pointless in a one-shot container.
            "OPENCLAW_DISABLE_BONJOUR": "1",
            # Keep the ACP stdout stream pure JSON-RPC.
            "OPENCLAW_HIDE_BANNER": "1",
            "OPENCLAW_SUPPRESS_NOTES": "1",
            "NO_COLOR": "1",
        })
        gateway_env = {**base, KEY_ENV: os.environ[KEY_ENV], TOKEN_ENV: token}

        # The Gateway's own console output goes to a file, never to ACP stdout.
        log_path = home / "gateway.log"
        with open(log_path, "wb") as log:
            gateway = subprocess.Popen(
                [str(OPENCLAW), "gateway", "run"], stdin=subprocess.DEVNULL,
                stdout=log, stderr=subprocess.STDOUT, env=gateway_env, cwd=str(home),
            )
        wait_ready(gateway, log_path)

        bridge = subprocess.Popen(
            [str(OPENCLAW), "acp", "--url", f"ws://127.0.0.1:{port}", "--token-file", str(token_file)],
            env=base,
        )

        def forward(signum, _frame):
            if bridge.poll() is None:
                bridge.send_signal(signum)

        signal.signal(signal.SIGTERM, forward)
        signal.signal(signal.SIGINT, forward)
        code = bridge.wait()
        return code if code >= 0 else 128 - code
    except (OSError, ValueError, RuntimeError) as exc:
        print(redact(str(exc)), file=sys.stderr)
        return 1
    finally:
        stop(bridge)
        stop(gateway)


if __name__ == "__main__":
    raise SystemExit(main())
