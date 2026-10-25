"""Select native MicroClaw config without replacing its runtime or tools."""
from __future__ import annotations
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit

def settings(environ, home):
    for name in ("ABB_AGENT_MODEL", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL_API_KEY"):
        if not environ.get(name, "").strip():
            raise ValueError(name + " is required")
    base = environ["ABB_AGENT_MODEL_BASE_URL"]
    u = urlsplit(base)
    if (u.scheme != "https" or not u.hostname or u.username or u.password or u.query or u.fragment
            or any(c.isspace() for c in base)):
        raise ValueError("Model base must be a credential-free HTTPS URL")
    model = environ["ABB_AGENT_MODEL"]
    if any(c.isspace() for c in model):
        raise ValueError("Model identifier must not contain whitespace")
    config = {"llm_provider": "openai", "api_key": environ["ABB_AGENT_MODEL_API_KEY"],
              "model": model, "llm_base_url": base.rstrip("/"),
              "aux_models": {name: model for name in ("compaction", "reflector", "title", "vision")},
              "fallback_model": None, "data_dir": str(Path(home) / "data"),
              "working_dir": "/home/agent/workspace", "working_dir_isolation": "direct",
              "channels": {"web": {"enabled": True, "host": "127.0.0.1", "port": 18080}}}
    # The native acp branch never starts the Web channel. Its regular Config::load
    # requires one configured channel; this flag satisfies that native validation.
    return ["/usr/local/bin/microclaw", "acp"], config

def prepare(environ):
    # Validate before creating state; each process gets independent HOME and data.
    settings(environ, "/tmp/validation-only")
    child = {k: v for k, v in environ.items() if not k.startswith("MICROCLAW_")}
    home = Path(tempfile.mkdtemp(prefix="abb-microclaw-"))
    command, config = settings(environ, home)
    path = home / "microclaw.config.yaml"
    with open(path, "x", encoding="utf-8", opener=lambda p, f: os.open(p, f, 0o600)) as output:
        json.dump(config, output)  # JSON is valid YAML, consumed by native serde_yaml.
    child["HOME"] = str(home)
    for key, relative in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                          ("XDG_CACHE_HOME", ".cache"), ("XDG_STATE_HOME", ".local/state")):
        directory = home / relative
        directory.mkdir(parents=True, exist_ok=True)
        child[key] = str(directory)
    child["MICROCLAW_CONFIG"] = str(path)
    # At the pinned source, this env flag selects native file logging only
    # (src/main.rs), keeping console logs out of ACP stdout. It starts no gateway.
    child["MICROCLAW_GATEWAY"] = "1"
    return command, child, home

def main():
    command, child, _ = prepare(dict(os.environ))
    os.execvpe(command[0], command, child)

if __name__ == "__main__":
    main()
