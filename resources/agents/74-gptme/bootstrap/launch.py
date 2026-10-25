"""Map the selected OpenAI-compatible model profile onto gptme's native ACP server."""
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
AGENT_BIN = "/opt/agent-venv/bin/gptme-acp"
TIKTOKEN_CACHE_DIR = "/opt/tiktoken-cache"
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-/:]*")
# Inherited settings that would re-point gptme away from the selected endpoint:
# the LLM proxy, and the legacy OPENAI_API_BASE, which gptme's `local` provider
# prefers over OPENAI_BASE_URL.
DROPPED_ENV = ("OPENAI_API_BASE", "LLM_PROXY_URL", "LLM_PROXY_API_KEY")


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return the ACP command and environment without persisting secrets."""
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

    child = {k: v for k, v in environ.items() if k not in DROPPED_ENV}
    child.update({
        # gptme's documented route for any OpenAI-compatible Chat Completions
        # server is the `local` provider: it reads OPENAI_BASE_URL and
        # OPENAI_API_KEY from the environment, so the key never reaches argv
        # or disk. GPTME_MODEL outranks every config-file MODEL setting.
        "OPENAI_API_KEY": key,
        "OPENAI_BASE_URL": base_url,
        "GPTME_MODEL": f"local/{model}",
        # The ACP worker passes only base and trust variables, not image ENV;
        # point tiktoken at the encodings baked in at build time (Dockerfile).
        "TIKTOKEN_CACHE_DIR": TIKTOKEN_CACHE_DIR,
    })
    return [AGENT_BIN], child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        # A disposable HOME keeps gptme's config, conversation logs and state
        # writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-gptme-home-"))
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
