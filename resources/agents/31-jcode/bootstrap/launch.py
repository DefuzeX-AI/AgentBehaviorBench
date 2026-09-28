"""Map an OpenAI-compatible GLM profile onto jcode's native ACP adapter and own its daemon.

`jcode acp` is a thin ACP front end: on the first `session/new` it spawns the
jcode daemon (`jcode serve`, detached with setsid) and talks to it over a Unix
socket. This launcher gives every Case a disposable HOME, JCODE_HOME and
socket directory, so the daemon, its sessions and its logs belong to exactly one
Case, and stops that daemon when the ACP process exits.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
JCODE_BIN = "/opt/jcode/bin/jcode"
PROFILE_ID = "abb-glm"
# Context windows of Zhipu GLM models (same values as upstream's bundled
# Z.AI metadata). Unknown models fall back to a conservative 128k window.
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


def toml_string(value: str) -> str:
    """Return a TOML basic string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def config_toml(base_url: str, model: str) -> str:
    """Return jcode's ~/.jcode/config.toml for one static OpenAI-compatible profile.

    The key is referenced by environment-variable name only; it is never written.
    """
    context = CONTEXT_LIMITS.get(model, DEFAULT_CONTEXT_LIMIT)
    return "\n".join([
        "[features]",
        # No self-update, no memory sidecar/recall model calls, no swarm workers.
        "check_updates = false",
        "memory = false",
        "swarm = false",
        "",
        "[sponsors]",
        # Integration discovery calls api.jcode.sh; not part of the evaluated route.
        "enabled = false",
        "",
        "[ambient]",
        "enabled = false",
        "",
        "[acp]",
        'profile = "standard"',
        'tool_profile = "acp"',
        "",
        "[provider]",
        f"default_provider = {toml_string(PROFILE_ID)}",
        f"default_model = {toml_string(model)}",
        'cross_provider_failover = "manual"',
        "same_provider_account_failover = false",
        "",
        f"[providers.{PROFILE_ID}]",
        'type = "openai-compatible"',
        f"base_url = {toml_string(base_url)}",
        f"api_key_env = {toml_string(KEY_ENV)}",
        f"default_model = {toml_string(model)}",
        "",
        f"[[providers.{PROFILE_ID}.models]]",
        f"id = {toml_string(model)}",
        f"context_window = {context}",
        "",
    ])


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], str]:
    """Return the jcode ACP command, child environment and config file text."""
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

    runtime_dir = home / "run"
    child = {
        **environ,
        KEY_ENV: key,
        "HOME": str(home),
        "JCODE_HOME": str(home / ".jcode"),
        # Daemon socket, spawn lock and API socket live here, per Case.
        "JCODE_RUNTIME_DIR": str(runtime_dir),
        "XDG_RUNTIME_DIR": str(runtime_dir),
        # Anonymous usage telemetry would be undeclared egress.
        "JCODE_NO_TELEMETRY": "1",
        "DO_NOT_TRACK": "1",
        # models.dev pricing catalog download (Cloudflare) at daemon start.
        "JCODE_DISABLE_PRICING_REFRESH": "1",
        "JCODE_NO_AUTO_UPDATE": "1",
        "JCODE_NO_BROWSER": "1",
        "JCODE_NO_MENUBAR": "1",
        "JCODE_DISABLE_POWER_INHIBIT": "1",
        # Keep the two tokio runtimes (ACP front end + daemon) inside the
        # container's pids limit; the default is one worker per host CPU.
        "TOKIO_WORKER_THREADS": environ.get("TOKIO_WORKER_THREADS", "4"),
    }
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        child[var] = str(home / sub)
    return [JCODE_BIN, "acp"], child, config_toml(base_url, model)


def stop_daemon(environ: dict[str, str], home: Path) -> None:
    """Stop this Case's jcode daemon, then kill anything still using its JCODE_HOME."""
    try:
        subprocess.run([JCODE_BIN, "server", "stop", "--json"], env=environ, stdin=subprocess.DEVNULL,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15, check=False)
    except (OSError, subprocess.SubprocessError):
        pass
    marker = f"JCODE_HOME={home / '.jcode'}".encode()
    deadline = time.monotonic() + 5
    while True:
        leftovers = []
        for entry in Path("/proc").iterdir():
            if not entry.name.isdigit() or int(entry.name) == os.getpid():
                continue
            try:
                if marker in (entry / "environ").read_bytes().split(b"\0"):
                    leftovers.append(int(entry.name))
            except OSError:
                continue
        if not leftovers:
            return
        final = time.monotonic() >= deadline
        for pid in leftovers:
            try:
                os.killpg(os.getpgid(pid), signal.SIGKILL if final else signal.SIGTERM)
            except OSError:
                try:
                    os.kill(pid, signal.SIGKILL if final else signal.SIGTERM)
                except OSError:
                    pass
        if final:
            return
        time.sleep(0.2)


def main() -> int:
    home = None
    environ: dict[str, str] = {}
    try:
        # A disposable HOME keeps jcode's config, sessions, sqlite databases and
        # logs writable by whichever unprivileged uid the runtime selects, and
        # isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-jcode-home-"))
        command, environ, config = prepare(dict(os.environ), home)
        (home / "run").mkdir(mode=0o700)
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            Path(environ[var]).mkdir(parents=True, exist_ok=True)
        jcode_home = home / ".jcode"
        jcode_home.mkdir()
        (jcode_home / "config.toml").write_text(config)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1

    # ACP stdio is inherited directly: jcode speaks spec ACP and needs no rewriting.
    child = subprocess.Popen(command, env=environ)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))
    try:
        return child.wait()
    finally:
        stop_daemon(environ, home)


if __name__ == "__main__":
    raise SystemExit(main())
