"""Configure the unchanged native ACP server from ABB's selected model."""
from __future__ import annotations
import json
import os
from pathlib import Path
import sys
import tempfile
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
    child.update(OPENAI_API_KEY=environ[KEY], OPENAI_BASE_URL=base,
                 PYDANTIC_DEEP_MODEL="openai:" + model)
    return ["/opt/agent-venv/bin/python", "/opt/agent/bootstrap/server.py"], child, {}

def main():
    command, child, _ = prepare(dict(os.environ))
    child, _ = isolated(child)
    os.execvpe(command[0], command, child)

if __name__ == "__main__":
    main()
