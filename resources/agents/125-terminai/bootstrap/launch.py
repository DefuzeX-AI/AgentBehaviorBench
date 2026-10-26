"""Launch TerminaI native ACP adapter with ABB dynamic model configuration."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"

TERMINAI_BUNDLE = "/opt/terminai/bundle/gemini.js"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Configure ~/.terminai/settings.json with OpenAI-compatible DeepSeek settings."""
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()

    if not key:
        key = environ.get("DEEPSEEK_API_KEY", "").strip()
    if not base_url:
        base_url = environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com").strip().rstrip("/")
    if not model:
        model = environ.get("DEEPSEEK_MODEL", "deepseek-chat").strip()

    if not key:
        raise ValueError(f"{KEY_ENV} is required")

    config_dir = home / ".terminai"
    config_dir.mkdir(parents=True, exist_ok=True)
    # Mark first-run onboarding as complete so TerminaI does not wait for interactive setup
    (config_dir / ".onboarded").write_text("2026-10-25T00:00:00.000Z")

    bin_dir = config_dir / "bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    rg_symlink = bin_dir / "rg"
    if not rg_symlink.exists() and Path("/usr/bin/rg").exists():
        try:
            rg_symlink.symlink_to("/usr/bin/rg")
        except OSError:
            pass

    settings_file = config_dir / "settings.json"

    # Write TerminaI settings
    settings = {
        "security": {
            "auth": {
                "selectedType": "use_openai_compatible"
            }
        },
        "llm": {
            "provider": "openai_compatible",
            "openaiCompatible": {
                "baseUrl": base_url,
                "model": model,
                "auth": {
                    "type": "bearer",
                    "envVarName": "DEEPSEEK_API_KEY"
                }
            }
        }
    }
    settings_file.write_text(json.dumps(settings, indent=2))

    child_env = dict(environ)
    child_env["HOME"] = str(home)
    child_env["DEEPSEEK_API_KEY"] = key
    child_env["OPENAI_API_KEY"] = key
    child_env["TERMINAI_ALLOW_DIRECT_HOST"] = "true"
    child_env["NODE_OPTIONS"] = "--require /opt/agent/bootstrap/dns_patch.js --max-old-space-size=1536"

    cmd = [
        "node",
        TERMINAI_BUNDLE,
        "--experimental-acp",
    ]
    return cmd, child_env


def relay(command: list[str], environ: dict[str, str], workspace: Path) -> int:
    """Relay stdio between harness and terminai ACP, routing non-JSON logs to stderr."""
    child = subprocess.Popen(
        command,
        env=environ,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=sys.stderr,
    )
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
    err = sys.stderr.buffer
    try:
        for line in child.stdout:
            # ACP lines are JSON-RPC objects
            stripped = line.strip()
            if stripped.startswith(b'{"jsonrpc"') or stripped.startswith(b"{\n"):
                out.write(line)
                out.flush()
            else:
                err.write(line)
                err.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


def open_directories(root: Path) -> None:
    """Ensure host can remove workspace entries without permission errors."""
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
        home = Path(tempfile.mkdtemp(prefix="abb-terminai-home-"))
        command, environ = prepare(dict(os.environ), home)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1

    os.umask(0)
    workspace = Path.cwd()
    try:
        return relay(command, environ, workspace)
    finally:
        open_directories(workspace)


if __name__ == "__main__":
    raise SystemExit(main())
