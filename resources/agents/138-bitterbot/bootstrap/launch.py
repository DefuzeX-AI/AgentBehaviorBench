"""Start an isolated native Bitterbot Gateway and its original ACP stdio bridge."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import signal
import subprocess
import sys
import tempfile
import threading
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
CLI = ROOT / "agent/bitterbot.mjs"
GATEWAY_PORT = 19001
READY_TIMEOUT = 180
BRIDGE_READY_TIMEOUT = 30


def model_config(env: dict[str, str]) -> tuple[str, str, str]:
    names = ("ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL")
    values = tuple(env.get(name, "").strip() for name in names)
    for name, value in zip(names, values):
        if not value:
            raise ValueError(f"{name} is required")
    key, url, model = values
    parsed = urlsplit(url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError("ABB_AGENT_MODEL_BASE_URL must be an HTTPS URL without query or fragment")
    return key, url.rstrip("/"), model


def gateway_config(url: str, model: str, workspace: str) -> dict:
    return {
        "gateway": {"mode": "local", "port": GATEWAY_PORT, "bind": "loopback",
                    "auth": {"mode": "token", "token": "${BITTERBOT_GATEWAY_TOKEN}"}},
        "agents": {"defaults": {"model": {"primary": f"abb/{model}"},
                                  "workspace": workspace, "skipBootstrap": True,
                                  "heartbeat": {"every": "0m"},
                                  "memorySearch": {"local": {"modelPath": str(ROOT / "models/embeddinggemma-300m-qat-Q8_0.gguf")}}}},
        "models": {"mode": "merge", "liveDiscovery": {"enabled": False},
                   "providers": {"abb": {"baseUrl": url,
                       "apiKey": "${ABB_AGENT_MODEL_API_KEY}", "api": "openai-completions",
                       "models": [{"id": model, "name": model, "reasoning": False,
                           "input": ["text"], "cost": {"input": 0, "output": 0,
                           "cacheRead": 0, "cacheWrite": 0},
                           "contextWindow": 128000, "maxTokens": 8192}]}}},
        # These optional services have no counterpart in a one-shot local Case.
        # No native tool allowlist, tool implementation or approval is changed.
        "p2p": {"enabled": False}, "circles": {"enabled": False},
        "memory": {"dream": {"enabled": False}}, "cron": {"enabled": False},
        "update": {"checkOnStart": False},
        "browser": {"headless": True, "defaultProfile": "bitterbot",
                    "executablePath": "/usr/bin/chromium",
                    "profiles": {"bitterbot": {"cdpPort": 18800, "color": "#FF4500"}}},
    }


def stop(proc: subprocess.Popen | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(10)



def bridge_connected(line: bytes) -> bool:
    return b"[acp] gateway reconnected" in line


def forward_bytes(source_fd: int, sink) -> None:
    try:
        while block := os.read(source_fd, 65536):
            sink.write(block)
            sink.flush()
    except (BrokenPipeError, OSError):
        pass
    finally:
        try:
            sink.close()
        except (BrokenPipeError, OSError):
            pass


def start_input_forwarder(bridge: subprocess.Popen) -> threading.Thread:
    thread = threading.Thread(target=forward_bytes,
                              args=(sys.stdin.fileno(), bridge.stdin), daemon=True)
    thread.start()
    return thread


def native_session_key() -> str:
    # Native Gateway canonicalizes short keys; the ACP bridge matches events by exact key.
    # Supply its documented canonical form and isolate it to this process/Case.
    return f"agent:main:abb-{secrets.token_hex(16)}"


def main() -> int:
    gateway = bridge = None
    stderr_thread = None
    stop_requested = threading.Event()
    sensitive: list[str] = []
    try:
        key, url, model = model_config(dict(os.environ))
        home = Path(tempfile.mkdtemp(prefix="abb-bitterbot-"))
        state = home / ".bitterbot"
        state.mkdir(mode=0o700)
        config_path = state / "bitterbot.json"
        config_path.touch(mode=0o600)
        config_path.write_text(json.dumps(gateway_config(url, model, os.getcwd()), indent=2))
        token = secrets.token_hex(32)
        sensitive = [key, token]
        env = {**os.environ, "HOME": str(home), "BITTERBOT_STATE_DIR": str(state),
               "BITTERBOT_CONFIG_PATH": str(config_path), "BITTERBOT_GATEWAY_TOKEN": token,
               "BITTERBOT_HIDE_BANNER": "1", "BITTERBOT_NO_RESPAWN": "1", "NO_COLOR": "1"}
        log_path = home / "gateway.log"
        with log_path.open("wb") as log:
            gateway = subprocess.Popen(["node", str(CLI), "gateway", "run"],
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                env=env, cwd=ROOT / "agent")
        deadline = time.monotonic() + READY_TIMEOUT
        while time.monotonic() < deadline:
            text = log_path.read_text(errors="replace")
            if "listening on ws://127.0.0.1:19001" in text:
                break
            if gateway.poll() is not None:
                raise RuntimeError(f"Bitterbot Gateway exited {gateway.returncode}:\n{text[-6000:]}")
            time.sleep(0.25)
        else:
            raise RuntimeError(f"Bitterbot Gateway readiness timed out:\n{log_path.read_text(errors='replace')[-6000:]}")
        # Use native config/env authentication, never a secret command argument.
        bridge = subprocess.Popen(["node", str(CLI), "acp", "--url",
                                   f"ws://127.0.0.1:{GATEWAY_PORT}", "--session",
                                   native_session_key(), "--verbose"],
                                  env=env, stdin=subprocess.PIPE, stderr=subprocess.PIPE)
        connected = threading.Event()
        def observe_stderr():
            for line in bridge.stderr:
                safe = line.replace(key.encode(), b"[REDACTED]").replace(token.encode(), b"[REDACTED]")
                sys.stderr.buffer.write(safe)
                sys.stderr.buffer.flush()
                if bridge_connected(line):
                    connected.set()
        stderr_thread = threading.Thread(target=observe_stderr, daemon=True)
        stderr_thread.start()
        def forward(signum, _frame):
            stop_requested.set()
            if bridge.poll() is None:
                bridge.send_signal(signum)
        signal.signal(signal.SIGTERM, forward)
        signal.signal(signal.SIGINT, forward)
        deadline = time.monotonic() + BRIDGE_READY_TIMEOUT
        while not connected.wait(0.1):
            if bridge.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError("Native ACP bridge did not complete its Gateway handshake")
        # Native initialize/newSession can answer before its WebSocket connects.
        # Gate only transport input until native onHelloOk; forward exact bytes.
        start_input_forwarder(bridge)
        while True:
            if gateway.poll() is not None and not stop_requested.is_set():
                details = log_path.read_text(errors="replace")[-6000:]
                for name in ("memory.events", "memory.peak"):
                    counter = Path("/sys/fs/cgroup") / name
                    if counter.exists():
                        details += f"\n{name}:\n{counter.read_text()}"
                raise RuntimeError(f"Native Gateway exited {gateway.returncode}:\n{details}")
            try:
                code = bridge.wait(timeout=0.2)
                return code if code >= 0 else 128 - code
            except subprocess.TimeoutExpired:
                pass
    except (OSError, ValueError, RuntimeError) as exc:
        message = str(exc)
        for value in sensitive:
            message = message.replace(value, "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    finally:
        stop(bridge)
        if stderr_thread is not None:
            stderr_thread.join(timeout=5)
        stop(gateway)


if __name__ == "__main__":
    raise SystemExit(main())
