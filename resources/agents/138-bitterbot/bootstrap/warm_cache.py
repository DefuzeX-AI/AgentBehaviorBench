"""Compile the original native plugin cache without network or Case execution."""
from __future__ import annotations

import json
import os
from pathlib import Path
import secrets
import shutil
import signal
import subprocess
import tempfile
import time

from launch import CLI, GATEWAY_PORT, gateway_config

CACHE = Path("/home/agent/.cache/bitterbot")


def main() -> None:
    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=CACHE, prefix="build-config-") as temporary:
        home = Path(temporary)
        state = home / ".bitterbot"
        state.mkdir()
        config = state / "bitterbot.json"
        config.write_text(json.dumps(gateway_config(
            "https://example.invalid/v1", "build-cache-only", str(home / "workspace"))))
        token, key = secrets.token_hex(32), secrets.token_urlsafe(32)
        env = {**os.environ, "HOME": str(home), "TMPDIR": str(CACHE),
               "BITTERBOT_CONFIG_PATH": str(config), "BITTERBOT_STATE_DIR": str(state),
               "BITTERBOT_GATEWAY_TOKEN": token, "ABB_AGENT_MODEL_API_KEY": key,
               "BITTERBOT_HIDE_BANNER": "1", "BITTERBOT_NO_RESPAWN": "1", "NO_COLOR": "1",
               # Build-time compilation only; normal Case memory policy is unchanged.
               "NODE_OPTIONS": "--max-old-space-size=1536"}
        log_path = home / "gateway.log"
        with log_path.open("wb") as log:
            proc = subprocess.Popen(["node", str(CLI), "gateway", "run"], env=env,
                stdin=subprocess.DEVNULL, stdout=log, stderr=subprocess.STDOUT,
                cwd=CLI.parent, start_new_session=True)
        ready = False
        try:
            deadline = time.monotonic() + 180
            while time.monotonic() < deadline:
                text = log_path.read_text(errors="replace")
                if f"listening on ws://127.0.0.1:{GATEWAY_PORT}" in text:
                    ready = True
                    break
                if proc.poll() is not None:
                    break
                time.sleep(0.2)
        finally:
            if proc.poll() is None:
                os.killpg(proc.pid, signal.SIGTERM)
                try:
                    proc.wait(5)
                except subprocess.TimeoutExpired:
                    os.killpg(proc.pid, signal.SIGKILL)
                    proc.wait(5)
        if not ready:
            text = log_path.read_text(errors="replace").replace(token, "[REDACTED]").replace(key, "[REDACTED]")
            raise RuntimeError("Native plugin cache warmup did not reach readiness:\n" + text[-6000:])
        count = len(list((CACHE / "jiti").glob("*")))
        if not count:
            raise RuntimeError("Native plugin cache warmup produced no Jiti files")
        print(f"Native Gateway reached readiness; retained {count} compiled plugin cache files")
    for path in CACHE.iterdir():
        if path.name != "jiti":
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()


if __name__ == "__main__":
    main()
