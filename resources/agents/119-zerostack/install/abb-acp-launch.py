"""ABB outer launcher for zerostack's ACP server (modelled on the other ACP unit launchers).

zerostack reads its model provider from a config file (docs/CONFIG.md: `ZS_CONFIG_DIR/config.toml`, `custom_providers`)
plus CLI flags `--provider` / `--model` (env ZS_PROVIDER / ZS_MODEL). This launcher:
  1. reads ABB's shared model selection ABB_AGENT_MODEL_API_KEY / ABB_AGENT_MODEL_BASE_URL / ABB_AGENT_MODEL
     (every shared profile is an OpenAI-compatible Chat Completions endpoint);
  2. points HOME, ZS_CONFIG_DIR and ZS_DATA_DIR at a disposable per-Case directory and writes config.toml with one
     custom provider `abb` = {provider_type "openai", base_url, api_key_env "ABB_AGENT_MODEL_API_KEY",
     api_style "completions"} (docs/CONFIG.md "custom_providers"). The key stays in the environment, never on disk;
     auto-update-prompts / auto-update-themes = false so no interactive y/N prompt can read stdin (the ACP channel);
  3. execs `zerostack --acp --provider abb --model <model>` (stdio ACP, binary built with `--features acp`).
No zerostack behaviour is changed; permission mode stays the default (standard), as for any user.
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

KEY_ENV, BASE_URL_ENV, MODEL_ENV = "ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"
BINARY = os.environ.get("ABB_ZEROSTACK_BIN", "/usr/local/bin/zerostack")


def q(value: str) -> str:
    return json.dumps(value)  # a JSON string literal is a valid TOML basic string


def prepare(environ):
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    for name, value in ((KEY_ENV, key), (BASE_URL_ENV, base_url), (MODEL_ENV, model)):
        if not value:
            raise ValueError(f"{name} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    if base_url.endswith("/chat/completions"):
        base_url = base_url[: -len("/chat/completions")]
    config = "\n".join([
        "# Written by the ABB launcher at container start.",
        'provider = "abb"',
        "auto-update-prompts = false",
        "auto-update-themes = false",
        "",
        "[custom_providers.abb]",
        'provider_type = "openai"',
        f"base_url = {q(base_url)}",
        f"api_key_env = {q(KEY_ENV)}",
        'api_style = "completions"',
        f"model = {q(model)}",
        "",
    ])
    home = Path(tempfile.mkdtemp(prefix="abb-zerostack-home-"))
    cfg_dir = home / ".config" / "zerostack"
    data_dir = home / ".local" / "share" / "zerostack"
    cfg_dir.mkdir(parents=True, mode=0o700)
    data_dir.mkdir(parents=True, mode=0o700)
    (cfg_dir / "config.toml").write_text(config, encoding="utf-8")
    child = dict(environ)
    child["HOME"] = str(home)
    child["ZS_CONFIG_DIR"] = str(cfg_dir)
    child["ZS_DATA_DIR"] = str(data_dir)
    child["XDG_CONFIG_HOME"] = str(home / ".config")
    child["XDG_DATA_HOME"] = str(home / ".local" / "share")
    for name in ("ZS_PROVIDER", "ZS_MODEL"):
        child.pop(name, None)
    return [BINARY, "--acp", "--provider", "abb", "--model", model], child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
    except Exception as exc:  # noqa: BLE001
        print(f"abb-acp-launch: {exc}", file=sys.stderr)
        return 2
    os.execvpe(command[0], command, environ)
    return 127


if __name__ == "__main__":
    sys.exit(main())
