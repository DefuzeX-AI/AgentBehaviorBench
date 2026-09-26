"""Map an OpenAI-compatible GLM profile onto oh-my-pi's custom-provider config and start `omp acp`."""
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
AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
BIN_DIR = AGENT_DIR / "node_modules/.bin"
OMP_CLI = AGENT_DIR / "node_modules/@oh-my-pi/pi-coding-agent/dist/cli.js"
# Written at image build by bootstrap/list_providers.ts from the locked catalog.
BUILTIN_PROVIDERS_FILE = Path(__file__).resolve().parents[1] / "builtin-providers.json"
# omp also registers keyless local providers (Ollama, llama.cpp, LM Studio)
# whenever they are not configured and probes them on loopback.
IMPLICIT_LOCAL_PROVIDERS = ["ollama", "llama.cpp", "lm-studio"]


def disabled_providers(builtin: list[str]) -> list[str]:
    """Every built-in provider except the configured one.

    After each session is created omp starts a background model refresh that
    probes keyless provider endpoints (e.g. hyper.charm.land, api.kilo.ai,
    zenmux.ai) and the models.dev catalog mirror (catalog.stencil.so) for every
    enabled built-in provider. None of them is used here and the runtime rejects
    the trace on undeclared egress, so all of them are disabled via omp's own
    `disabledProviders` setting instead of being allowlisted.
    """
    return sorted((set(builtin) | set(IMPLICIT_LOCAL_PROVIDERS)) - {PROVIDER})


def prepare(environ: dict[str, str], builtin: list[str]) -> tuple[list[str], dict[str, str], dict[str, dict]]:
    """Return the omp command, its environment and omp config files without persisting secrets."""
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

    # JSON is valid YAML; omp parses models.yml / config.yml with a YAML loader.
    models = {
        "providers": {
            PROVIDER: {
                "baseUrl": base_url,
                "api": "openai-completions",
                # omp resolves an environment variable *name* here at request
                # time, so the credential is never written to disk or argv.
                "apiKey": KEY_ENV,
                "models": [{
                    "id": model,
                    "name": model,
                    "reasoning": True,
                    "contextWindow": 200000,
                    "maxTokens": 32000,
                    # GLM rejects the OpenAI "developer" role.
                    "compat": {"supportsDeveloperRole": False},
                }],
            }
        }
    }
    # ACP session/new does not pick a model, so omp must start on GLM by default.
    config = {
        "modelRoles": {"default": f"{PROVIDER}/{model}"},
        "disabledProviders": disabled_providers(builtin),
    }
    child = {
        **environ,
        # omp's own OTLP exporter only starts when an OTEL_* endpoint is set;
        # keep it off explicitly so no exporter traffic leaves the container.
        "OTEL_SDK_DISABLED": "true",
        # npm's own update check is noise. npm itself stays online for the bash
        # tool: the registry is on ABB's egress-observer allowlist.
        "npm_config_update_notifier": "false",
    }
    command = [str(BIN_DIR / "bun"), str(OMP_CLI), "acp"]
    return command, child, {"models.yml": models, "config.yml": config}


def main() -> int:
    try:
        builtin = json.loads(BUILTIN_PROVIDERS_FILE.read_text())
        command, environ, files = prepare(dict(os.environ), builtin)
        # A disposable HOME keeps omp's config, sessions, logs, model cache and
        # Bun's transpiler cache writable by whichever unprivileged uid the
        # runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-omp-home-"))
        agent_dir = home / ".omp/agent"
        agent_dir.mkdir(parents=True)
        for name, content in files.items():
            path = agent_dir / name
            path.write_text(json.dumps(content, indent=2))
            path.chmod(0o600)
        environ["HOME"] = str(home)
        environ["PI_CODING_AGENT_DIR"] = str(agent_dir)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:  # json.JSONDecodeError is a ValueError
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
