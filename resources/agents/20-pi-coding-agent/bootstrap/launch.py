"""Map an OpenAI-compatible GLM profile onto Pi's custom-provider config and start pi-acp."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
PROVIDER = "glm"
BIN_DIR = Path(__file__).resolve().parents[1] / "agent/node_modules/.bin"


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict[str, dict]]:
    """Return the pi-acp command, its environment and Pi config files without persisting secrets."""
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

    models = {
        "providers": {
            PROVIDER: {
                "baseUrl": base_url,
                "api": "openai-completions",
                # Pi resolves "$NAME" from the environment at request time, so
                # the credential is never written to disk or placed in argv.
                "apiKey": f"${KEY_ENV}",
                # GLM rejects the OpenAI "developer" role and uses Z.ai-style
                # thinking parameters instead of OpenAI reasoning_effort.
                "compat": {"supportsDeveloperRole": False, "thinkingFormat": "zai"},
                "models": [{"id": model, "reasoning": True, "contextWindow": 200000, "maxTokens": 32000}],
            }
        }
    }
    # ACP session/new does not pick a model, so Pi must start on GLM by default.
    settings = {
        "defaultProvider": PROVIDER,
        "defaultModel": model,
        "quietStartup": True,
        "enableInstallTelemetry": False,
    }
    child = {
        **environ,
        # Disables Pi's startup network operations: the pi.dev latest-version
        # check, install/update telemetry, package updates and fd/rg downloads.
        # None of them is on the admitted model route.
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        # Also turns off provider attribution headers.
        "PI_TELEMETRY": "0",
        # npm's own update check is noise. npm itself stays online: the npm
        # registry is on ABB's egress-observer allowlist, so pi-acp's
        # `npm view` update notice and `npm install` in Pi's bash tool work.
        "npm_config_update_notifier": "false",
        # pi-acp spawns `pi --mode rpc`; pin it to the locked install.
        "PI_ACP_PI_COMMAND": str(BIN_DIR / "pi"),
    }
    command = [str(BIN_DIR / "pi-acp")]
    return command, child, {"models.json": models, "settings.json": settings}


def main() -> int:
    try:
        command, environ, files = prepare(dict(os.environ))
        # A disposable HOME keeps Pi's config, sessions and pi-acp's session map
        # writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-pi-home-"))
        agent_dir = home / ".pi/agent"
        agent_dir.mkdir(parents=True)
        for name, content in files.items():
            path = agent_dir / name
            path.write_text(json.dumps(content, indent=2))
            path.chmod(0o600)
        environ["HOME"] = str(home)
        environ["PI_CODING_AGENT_DIR"] = str(agent_dir)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
