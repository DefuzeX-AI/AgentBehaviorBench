"""Map an OpenAI-compatible GLM profile onto the OpenHands CLI's native ACP server."""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
OPENHANDS_BIN = Path("/opt/openhands/bin")
EXTENSIONS_URL = "https://github.com/OpenHands/extensions"
EXTENSIONS_MIRROR = "file:///opt/openhands-extensions.git"
# load_public_skills=True is hardcoded and clones/fetches
# github.com/OpenHands/extensions every session. Map that URL to the pinned
# mirror baked into the image. Git honors safe.directory (needed because the
# mirror is root-owned and the runtime uid differs) only from global/system
# config, not from GIT_CONFIG_* variables, so this goes into $HOME/.gitconfig.
GITCONFIG = (
    f'[url "{EXTENSIONS_MIRROR}"]\n'
    f"\tinsteadOf = {EXTENSIONS_URL}\n"
    "[safe]\n"
    "\tdirectory = /opt/openhands-extensions.git\n"
)
# In ACP mode OpenHands 1.16.0 rejects session/new with "Authentication required"
# unless ~/.openhands/agent_settings.json exists, and it ignores
# --override-with-envs. Persist the agent spec once from the LLM_* variables with
# the CLI's own store, exactly as `openhands --override-with-envs` would.
WRITE_SETTINGS = (
    "from openhands_cli.stores.agent_store import AgentStore as S\n"
    "s = S()\n"
    "s.save(s.load_or_create(env_overrides_enabled=True))\n"
)


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict[str, str]]:
    """Return the ACP command, its environment, and the one-shot settings environment."""
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

    base = {k: v for k, v in environ.items() if k not in (KEY_ENV, "LLM_API_KEY")}
    base.update({
        "HOME": str(home),
        "XDG_CONFIG_HOME": str(home / ".config"),
        "XDG_CACHE_HOME": str(home / ".cache"),
        "XDG_DATA_HOME": str(home / ".local/share"),
        "XDG_STATE_HOME": str(home / ".local/state"),
        "OPENHANDS_SUPPRESS_BANNER": "1",
        # LiteLLM otherwise downloads its model cost map from
        # raw.githubusercontent.com at import time (undeclared egress).
        "LITELLM_LOCAL_MODEL_COST_MAP": "True",
        "GIT_TERMINAL_PROMPT": "0",
    })
    # LiteLLM's openai/ provider posts to <base>/chat/completions. The key only
    # reaches the settings writer through its environment, never argv.
    settings_env = {
        **base,
        "LLM_API_KEY": key,
        "LLM_BASE_URL": base_url,
        "LLM_MODEL": f"openai/{model}",
    }
    # Default confirmation mode is "always-ask": every action is sent to ABB as
    # session/request_permission and answered by permission_policy=allow_once.
    command = [str(OPENHANDS_BIN / "openhands"), "acp"]
    return command, base, settings_env


def main() -> int:
    key = os.environ.get(KEY_ENV) or "\0"
    try:
        # A disposable HOME keeps OpenHands' settings, skill cache and
        # conversations writable by whichever unprivileged uid the runtime
        # selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-openhands-home-"))
        (home / ".gitconfig").write_text(GITCONFIG)
        command, environ, settings_env = prepare(dict(os.environ), home)
        # stdout is the ACP channel; the writer's output goes to stderr.
        done = subprocess.run(
            [str(OPENHANDS_BIN / "python"), "-c", WRITE_SETTINGS],
            env=settings_env, cwd=os.getcwd(), stdin=subprocess.DEVNULL,
            stdout=sys.stderr, stderr=sys.stderr, timeout=300, check=False,
        )
        settings = home / ".openhands/agent_settings.json"
        if done.returncode != 0 or not settings.is_file():
            raise RuntimeError(f"writing {settings} failed (exit {done.returncode})")
        settings.chmod(0o600)
        os.execve(command[0], command, environ)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as exc:
        print(str(exc).replace(key, "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
