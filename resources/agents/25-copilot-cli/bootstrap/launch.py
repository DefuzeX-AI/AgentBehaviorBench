"""Map an OpenAI-compatible GLM profile onto GitHub Copilot CLI's native ACP server (BYOK, offline)."""
from __future__ import annotations

import os
from pathlib import Path
import platform
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
# glm-5.1 is not in Copilot's built-in model catalog, so without these the CLI
# warns and falls back to generic limits. Values stay below GLM's published
# context window and output cap.
MAX_PROMPT_TOKENS = "128000"
MAX_OUTPUT_TOKENS = "16384"
# Any of these would make Copilot authenticate against GitHub instead of staying
# in BYOK mode; this unit deliberately runs without a GitHub account.
GITHUB_TOKEN_ENVS = ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN")


def copilot_binary() -> str:
    """Prefer the native platform binary; fall back to the npm loader."""
    arch = {"x86_64": "x64", "amd64": "x64", "aarch64": "arm64", "arm64": "arm64"}.get(platform.machine().lower())
    native = AGENT_DIR / f"node_modules/@github/copilot-linux-{arch}/copilot"
    if arch and native.is_file() and os.access(native, os.X_OK):
        # Exec'ing the native binary directly avoids keeping an extra Node.js
        # loader process (npm-loader.js spawnSync) resident under the 1g limit.
        return str(native)
    return str(AGENT_DIR / "node_modules/.bin/copilot")


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return the Copilot ACP command and environment without persisting secrets."""
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

    child = {name: value for name, value in environ.items() if name not in GITHUB_TOKEN_ENVS}
    child.update({
        # Copilot's documented BYOK variables; the key never appears in argv,
        # where process listings and evidence could capture it.
        "COPILOT_PROVIDER_BASE_URL": base_url,
        "COPILOT_PROVIDER_API_KEY": key,
        "COPILOT_PROVIDER_TYPE": "openai",
        "COPILOT_PROVIDER_WIRE_API": "completions",
        "COPILOT_PROVIDER_MAX_PROMPT_TOKENS": MAX_PROMPT_TOKENS,
        "COPILOT_PROVIDER_MAX_OUTPUT_TOKENS": MAX_OUTPUT_TOKENS,
        # ACP session/new does not pick a model; select GLM at startup.
        "COPILOT_MODEL": model,
        # Offline mode skips GitHub auth, telemetry, web tools, the GitHub MCP
        # server and auto-update; all of these would be undeclared egress.
        "COPILOT_OFFLINE": "true",
        "COPILOT_AUTO_UPDATE": "false",
        "NO_COLOR": "1",
    })
    # OpenTelemetry export is only enabled when these are set; keep it off.
    for name in ("COPILOT_OTEL_ENABLED", "OTEL_EXPORTER_OTLP_ENDPOINT", "COPILOT_OTEL_FILE_EXPORTER_PATH"):
        child.pop(name, None)
    command = [copilot_binary(), "--acp", "--no-auto-update"]
    return command, child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        # A disposable HOME keeps Copilot's config and session state writable by
        # whichever unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-copilot-home-"))
        environ["HOME"] = str(home)
        environ["COPILOT_HOME"] = str(home / ".copilot")
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
