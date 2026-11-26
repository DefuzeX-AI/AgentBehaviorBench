"""Map the selected OpenAI-compatible model profile onto Sudo Code's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

import model_relay


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
SCODE = "/opt/scode/bin/scode"
# sudocode.json names: one api-key connection and one model alias that maps to it.
PROVIDER = "abb"
ALIAS = "abb"
PERMISSION_MODE = "workspace-write"
# Credentials and overrides scode would otherwise pick up for built-in providers,
# proxy accounts, Nexus, web search or an alternative config home.
FOREIGN_KEYS = (
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL", "ANTHROPIC_MODEL",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CONFIG_DIR", "OPENAI_API_KEY", "OPENAI_BASE_URL",
    "XAI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY", "DASHSCOPE_API_KEY",
    "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "PROXY_AUTH_TOKEN", "PROXY_BASE_URL",
    "CODEX_HOME", "CODEX_BASE_URL", "NEXUS_API_KEY", "BOCHA_API_KEY",
    "SUDOCODE_TAVILY_API_KEY", "SUDO_CODE_CONFIG_HOME", "SUDO_CODE_PERMISSION_MODE",
)


def render_config(base_url: str, model: str) -> str:
    """Return the sudocode.json that defines only the selected model."""
    config = {
        "auth_modes": {
            "api-key": {
                # scode reads the key from this variable; it is never written here.
                PROVIDER: {"baseUrl": base_url, "apiKeyEnv": KEY_ENV},
            },
        },
        "models": {
            ALIAS: {
                "alias": ALIAS,
                "name": model,
                "input": ["text"],
                "providers": {
                    # Chat Completions posts to <baseUrl>/chat/completions; the relay forwards
                    # it to the selected endpoint, the admitted route.
                    "api-key": {"provider": PROVIDER, "model": model, "api": "openai-completions"},
                },
            },
        },
    }
    return json.dumps(config, indent=2) + "\n"


def validated(environ: dict[str, str]) -> tuple[str, str]:
    """Return the base URL and model after checking the three model variables."""
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
    return base_url, model


def prepare(environ: dict[str, str], root: Path, base_url: str, model: str) -> tuple[list[str], dict[str, str]]:
    """Write the disposable scode config under root and return command and environment.

    base_url is the loopback model relay (see model_relay.py), which must not go
    through the runtime proxy.
    """
    global_dir = root / "global"
    project_dir = root / "project"
    for path in (global_dir, project_dir):
        path.mkdir(parents=True, exist_ok=True)
    (global_dir / "sudocode.json").write_text(render_config(base_url, model))

    no_proxy = ",".join(filter(None, [environ.get("NO_PROXY", ""), "127.0.0.1", "localhost"]))
    child = dict(environ)
    for name in FOREIGN_KEYS:
        child.pop(name, None)
    child.update({
        # Global config, model catalog cache and mailbox state stay out of the Case
        # workspace. An absolute project directory also keeps the project config
        # layer (and the memory directory scode derives from it) outside the
        # workspace, so a Case cannot redirect the provider by writing
        # <workspace>/.nexus/sudocode/sudocode.json.
        "SCODE_GLOBAL_CONFIG_DIR": str(global_dir),
        "SCODE_PROJECT_CONFIG_DIR": str(project_dir),
        "SCODE_LOG_PATH": str(root / "scode.log"),
        # Release update checks only run in interactive terminals; keep them off.
        "SCODE_CHECK_UPDATES": "0",
        "USER": environ.get("USER") or "agent",
        "NO_PROXY": no_proxy,
        "no_proxy": no_proxy,
    })
    command = [SCODE, "--model", ALIAS, "--auth", "api-key", "--permission-mode", PERMISSION_MODE, "acp"]
    return command, child


def main() -> int:
    try:
        environ = dict(os.environ)
        base_url, model = validated(environ)
        root = Path(tempfile.mkdtemp(prefix="abb-scode-"))
        _, relay_url = model_relay.start(base_url)
        command, child_env = prepare(environ, root, relay_url, model)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    # scode runs as a child so the relay thread stays alive; it inherits the ACP
    # stdio directly.
    child = subprocess.Popen(command, env=child_env)
    signal.signal(signal.SIGTERM, lambda *_: child.terminate())
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
