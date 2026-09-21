"""Map an OpenAI-compatible GLM profile onto deepagents-code's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
AGENT_BIN = "/opt/agent-venv/bin/deepagents-code"
MODEL_PATTERN = re.compile(r"[A-Za-z0-9][A-Za-z0-9._\-/]*")


def config_toml(base_url: str, model: str) -> str:
    """Return ~/.deepagents/config.toml; json.dumps emits valid TOML basic strings."""
    return "\n".join([
        "[models]",
        f"default = {json.dumps('openai:' + model)}",
        "",
        "[models.providers.openai]",
        f"base_url = {json.dumps(base_url)}",
        # The key stays in the environment; the config only names the variable.
        f"api_key_env = {json.dumps(KEY_ENV)}",
        f"models = [{json.dumps(model)}]",
        "",
        "[models.providers.openai.params]",
        # Without this langchain-openai uses the Responses API (POST .../responses),
        # which the GLM coding endpoint does not serve (404).
        "use_responses_api = false",
        "",
        "[update]",
        # Both default to network fetches (PyPI update check, GitHub-hosted price
        # list) outside the admitted model route.
        "check = false",
        "prices_auto_update = false",
        "",
    ])


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], str]:
    """Return the ACP command, environment, and config text without persisting secrets."""
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

    child = {k: v for k, v in environ.items() if not k.startswith(("LANGSMITH_", "LANGCHAIN_"))}
    child.update({
        KEY_ENV: key,
        # No managed ripgrep download (the image ships ripgrep from Debian).
        "DEEPAGENTS_CODE_OFFLINE": "1",
        # Belt and braces for the [update] config: no update/price/plugin fetches.
        "DEEPAGENTS_CODE_NO_UPDATE_CHECK": "1",
        "DEEPAGENTS_CODE_AUTO_UPDATE": "0",
        "DEEPAGENTS_CODE_PRICES_AUTO_UPDATE": "0",
        "DEEPAGENTS_CODE_PLUGIN_AUTO_UPDATE": "0",
        # No probe of a local Ollama daemon.
        "DEEPAGENTS_CODE_OLLAMA_DISCOVERY": "0",
        # Auto-save prompts the agent to persist "learnings" into ~/.deepagents
        # memory files outside the Case workspace; HOME is disposable, so those
        # writes would only add tool calls unrelated to the Case.
        "DEEPAGENTS_CODE_MEMORY_AUTO_SAVE": "0",
        # A project .env in the workspace must not re-point the model provider.
        "DEEPAGENTS_CODE_READ_PROJECT_DOTENV": "0",
        # LangSmith tracing would send runs to api.smith.langchain.com.
        "LANGSMITH_TRACING": "false",
        "LANGCHAIN_TRACING_V2": "false",
    })
    return [AGENT_BIN, "--acp"], child, config_toml(base_url, model)


def main() -> int:
    try:
        command, environ, config = prepare(dict(os.environ))
        # A disposable HOME keeps deepagents' config, sqlite sessions and state
        # writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-deepagents-home-"))
        (home / ".deepagents").mkdir()
        (home / ".deepagents/config.toml").write_text(config, encoding="utf-8")
        # Empty user skills dir: otherwise startup logs a path_not_found warning.
        (home / ".agents/skills").mkdir(parents=True)
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
