#!/usr/bin/env python3
"""Start Octop's inbound ACP server for one ABB Case.

Octop keeps its state under ``OCTOP_HOME`` (a SQLite control plane plus per-agent
workspaces). This launcher builds a disposable home for the Case, registers the
runtime model endpoint as an OpenAI-compatible provider, creates one agent whose
workspace and shell backend are rooted at the Case workspace, and then hands stdio
to ``octop acp``.

The CLI writes progress text to stdout; every call here captures it so that the
only bytes on stdout belong to the ACP protocol.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"

OCTOP = "/opt/octop/bin/octop"
HOME_DIR = Path(os.environ.get("OCTOP_HOME") or "/home/agent/.octop")
WORKSPACE = "/home/agent/workspace"
PROVIDER_NAME = "abb"
AGENT_NAME = "abb"
ADMIN_USER = "admin"
# Octop rejects passwords without both letters and digits; nothing authenticates
# against this account in ACP mode and the home is discarded per run.
ADMIN_PASSWORD = "abb-local-2026"


def log(message: str) -> None:
    sys.stderr.write(f"[octop-launch] {message}\n")
    sys.stderr.flush()


def run(args: list[str], *, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Run an Octop CLI command against the Case home, capturing its stdout."""
    environ = dict(os.environ)
    environ["OCTOP_HOME"] = str(HOME_DIR)
    proc = subprocess.run([OCTOP, *args], capture_output=True, text=True, env=environ)
    if check and proc.returncode != 0:
        log(f"command failed ({proc.returncode}): octop {' '.join(args)}")
        log(f"stdout: {proc.stdout.strip()[:2000]}")
        log(f"stderr: {proc.stderr.strip()[:2000]}")
        raise SystemExit(1)
    return proc


def database() -> Path:
    candidates = sorted(HOME_DIR.glob("*.db")) + sorted(HOME_DIR.glob("*.sqlite*"))
    if not candidates:
        log(f"no control-plane database under {HOME_DIR}")
        raise SystemExit(1)
    return candidates[0]


def configure(api_key: str, base_url: str, model: str) -> str:
    """Initialise the control plane and return the created agent id."""
    run(["init", "--admin-username", ADMIN_USER,
         "--admin-password", ADMIN_PASSWORD, "--yes"])

    models = json.dumps([{"id": model, "name": model}])
    run(["provider", "create",
         "--name", PROVIDER_NAME,
         "--kind", "openai",
         "--base-url", base_url,
         "--api-key", api_key,
         "--models", models])

    run(["agent", "create", AGENT_NAME, "--default-model", model, "--user", ADMIN_USER])

    connection = sqlite3.connect(database())
    try:
        row = connection.execute(
            "SELECT agent_id FROM agents WHERE name = ?", (AGENT_NAME,)).fetchone()
    finally:
        connection.close()
    if row is None:
        log(f"agent {AGENT_NAME!r} was not created")
        raise SystemExit(1)
    return str(row[0])


def pin_workspace(agent_id: str) -> None:
    """Point Octop's host-side workspace bookkeeping at the Case workspace.

    The shell backend is left at the harness default (rooted at ``/``) on purpose:
    Case prompts address ``/home/agent/workspace`` by absolute path, and a backend
    rooted at the workspace resolves that to a nested ``workspace/home/agent/...``
    directory, which makes the agent chase a path that appears not to exist. The
    container is the sandbox here, so host-rooted tools are the correct scope.
    """
    target = database()
    connection = sqlite3.connect(target)
    try:
        row = connection.execute(
            "SELECT config_json FROM agents WHERE agent_id = ?", (agent_id,)).fetchone()
        if row is None:
            log(f"agent {agent_id} missing from {target.name}")
            raise SystemExit(1)
        config = json.loads(row[0] or "{}")
        config["workspace_dir"] = WORKSPACE
        config.pop("backend", None)
        with connection:
            connection.execute(
                "UPDATE agents SET config_json = ? WHERE agent_id = ?",
                (json.dumps(config), agent_id))
    finally:
        connection.close()
    log(f"workspace pinned to {WORKSPACE} (shell backend stays host-rooted)")


def main() -> None:
    api_key = os.environ.get(KEY_ENV, "").strip()
    base_url = os.environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = os.environ.get(MODEL_ENV, "").strip()
    log(f"model={model or '-'} base_url={base_url or '-'} "
        f"key={'set' if api_key else 'missing'} proxy={os.environ.get('HTTPS_PROXY', '-')}")
    if not api_key or not base_url or not model:
        log("missing model settings; expected ABB_AGENT_MODEL_API_KEY, "
            "ABB_AGENT_MODEL_BASE_URL and ABB_AGENT_MODEL")
        raise SystemExit(1)

    if HOME_DIR.exists():
        shutil.rmtree(HOME_DIR, ignore_errors=True)
    HOME_DIR.mkdir(parents=True, exist_ok=True)
    Path(WORKSPACE).mkdir(parents=True, exist_ok=True)

    agent_id = configure(api_key, base_url, model)
    pin_workspace(agent_id)
    log(f"agent={agent_id}; starting ACP server")

    environ = dict(os.environ)
    environ["OCTOP_HOME"] = str(HOME_DIR)
    os.execve(OCTOP, [OCTOP, "acp", "--agent", agent_id], environ)


if __name__ == "__main__":
    main()
