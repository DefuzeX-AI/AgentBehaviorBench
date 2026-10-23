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
    settings = {"defaultModel": "abb", "models": {"abb": {
        "protocol": "openai-chat", "model": model, "baseURL": base,
        "apiKey": "${ABB_AGENT_MODEL_API_KEY}"}}}
    return ["node", "/opt/agent/agent/dist/eagent.js", "--acp", "--model", "abb"], dict(environ), settings

def main():
    command, child, settings = prepare(dict(os.environ))
    child, home = isolated(child)
    (home / ".easy-agent").mkdir()
    (home / ".easy-agent/settings.json").write_text(json.dumps(settings))
    # Native fetch/Node TLS honors NODE_EXTRA_CA_CERTS before first use.
    if child.get("SSL_CERT_FILE"):
        child["NODE_EXTRA_CA_CERTS"] = child["SSL_CERT_FILE"]
    os.execvpe(command[0], command, child)

if __name__ == "__main__":
    main()
