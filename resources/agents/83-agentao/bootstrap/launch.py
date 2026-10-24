"""Map the selected OpenAI-compatible model profile onto Agentao's native ACP server."""
from __future__ import annotations

import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
AGENT_BIN = "/opt/agent-venv/bin/agentao"
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-/]*")
# Agentao resolves ``{PROVIDER}_API_KEY`` / ``_BASE_URL`` / ``_MODEL`` under the
# provider named by ``LLM_PROVIDER``; one fixed block keeps the mapping explicit.
PROVIDER = "ABB"
# Provider blocks and LLM tuning a workspace .env or the image environment
# could otherwise contribute; the launch environment is Agentao's top layer.
STRIPPED_PREFIXES = ("OPENAI_", "ANTHROPIC_", "DEEPSEEK_", "GEMINI_", "LLM_")


def provider_block(base_url: str, model: str) -> dict[str, str]:
    """Return Agentao's non-secret provider-prefixed LLM settings."""
    return {
        "LLM_PROVIDER": PROVIDER,
        f"{PROVIDER}_BASE_URL": base_url,
        f"{PROVIDER}_MODEL": model,
        # The selected endpoints speak Chat Completions.
        f"{PROVIDER}_API_FORMAT": "openai-completions",
    }


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return the ACP command, child environment and provider block without persisting secrets."""
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    if not base_url:
        raise ValueError(f"{BASE_URL_ENV} is required")
    if not model:
        raise ValueError(f"{MODEL_ENV} is required")
    if not MODEL_PATTERN.fullmatch(model):
        raise ValueError(f"{MODEL_ENV} contains unsupported characters")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")

    child = {k: v for k, v in environ.items() if not k.startswith(STRIPPED_PREFIXES)}
    child.pop(KEY_ENV, None)
    block = provider_block(base_url, model)
    child.update(block)
    child[f"{PROVIDER}_API_KEY"] = key
    return [AGENT_BIN, "--acp"], child, block


def main() -> int:
    try:
        command, environ, _ = prepare(dict(os.environ))
        # A disposable HOME keeps ~/.agentao (login file, memory, sessions,
        # logs) writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case; no stale llm.json can override the selected model.
        home = Path(tempfile.mkdtemp(prefix="abb-agentao-home-"))
        environ["HOME"] = str(home)
        for name, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                          ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
            (home / sub).mkdir(parents=True, exist_ok=True)
            environ[name] = str(home / sub)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
