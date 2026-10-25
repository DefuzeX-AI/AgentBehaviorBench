"""Configure the unchanged native ACP server from ABB's selected model."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
import subprocess
import signal
from urllib.parse import urlsplit
KEY = "ABB_AGENT_MODEL_API_KEY"
BASE = "ABB_AGENT_MODEL_BASE_URL"
MODEL = "ABB_AGENT_MODEL"

def selected(environ):
    for name in (KEY, BASE, MODEL):
        if not environ.get(name, "").strip():
            raise ValueError(name + " is required")
    base = environ[BASE].rstrip("/")
    u = urlsplit(base)
    if u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment:
        raise ValueError("Model base must be a credential-free HTTPS URL")
    if any(c.isspace() for c in environ[MODEL]):
        raise ValueError("Model identifier must not contain whitespace")
    return base, environ[MODEL]

def isolated(environ):
    child = dict(environ)
    home = Path(tempfile.mkdtemp(prefix="abb-native-home-"))
    child["HOME"] = str(home)
    for key, directory in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                           ("XDG_CACHE_HOME", ".cache"), ("XDG_STATE_HOME", ".local/state")):
        path = home / directory
        path.mkdir(parents=True, exist_ok=True)
        child[key] = str(path)
    return child, home

def prepare(environ):
    base, model = selected(environ)
    child = dict(environ)
    child.update(LLM_PROVIDER="OPENAI", LLM_MODEL=model, OPENAI_MODEL=model,
                 OPENAI_ASSISTANT_MODEL=model, OPENAI_API_URL=base + "/chat/completions",
                 OPENAI_API_KEY=environ[KEY])
    return ["/usr/local/bin/chatcli", "acp"], child, {}

def main():
    command, child, _ = prepare(dict(os.environ))
    child, _ = isolated(child)
    from compat import serve
    server, endpoint = serve(child["OPENAI_API_URL"])
    child["OPENAI_API_URL"] = endpoint
    process = None
    def forward(signum, frame):
        if process is not None and process.poll() is None:
            process.send_signal(signum)
    for signum in (signal.SIGTERM, signal.SIGINT):
        signal.signal(signum, forward)
    try:
        process = subprocess.Popen(command, env=child)
        code = process.wait()
    finally:
        server.shutdown()
        server.server_close()
    raise SystemExit(code)

if __name__ == "__main__":
    main()
