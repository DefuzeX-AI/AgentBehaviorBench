"""Map the selected OpenAI-compatible model profile onto Cline CLI's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
# The pinned ACP CLI silently defaults unknown models. Select a native provider
# and validate its bundled catalog instead of using its generic-provider fallback.
PROVIDERS = {"openrouter": "openrouter", "deepseek": "deepseek", "glm": "zhipuai"}
CATALOG = json.loads((Path(__file__).with_name("model-catalog.json")).read_text(encoding="utf-8"))["models"]
GLOBAL_SETTINGS = {
    # Cline sends OpenTelemetry to otel.cline.bot unless the user opts out, and
    # checks npm for updates; both are egress outside the admitted model route.
    "telemetryOptOut": True,
    "autoUpdateEnabled": False,
}


def provider_settings(base_url: str, model: str, provider: str) -> dict:
    """Cline's providers.json with the base URL override; the key stays in env."""
    return {
        "version": 1,
        "providers": {
            provider: {
                "settings": {"provider": provider, "baseUrl": base_url, "model": model,
                             "modelCatalog": {"loadLatestOnInit": False, "loadPrivateOnAuth": False}},
                "updatedAt": "2026-09-21T00:00:00.000Z",
                "tokenSource": "manual",
            }
        },
        "lastUsedProvider": provider,
    }


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], str, str]:
    """Return the Cline ACP command and environment without persisting secrets."""
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

    provider = PROVIDERS.get(environ.get("ABB_AGENT_MODEL_PROVIDER", ""))
    if provider is None:
        raise ValueError("Cline supports shared openrouter, deepseek and glm profiles")
    if model not in CATALOG[provider]:
        raise ValueError(f"Requested model is not in Cline's pinned {provider} catalog; no fallback was made")

    child = {
        **environ,
        # ACP session/new answers "Authentication required" unless CLINE_API_KEY
        # is set; Cline then uses it as the selected provider's key. Passing it
        # through the environment keeps it out of argv and out of files.
        "CLINE_API_KEY": key,
        "CLINE_PROVIDER": provider,
        "CLINE_MODEL": model,
        "CLINE_NO_AUTO_UPDATE": "1",
        "DO_NOT_TRACK": "1",
        # The default "auto" session backend polls a shared background hub
        # daemon at http://127.0.0.1:25463/health (and would start one). The
        # interceptor rejects that loopback request as undeclared egress; the
        # one-shot container only needs Cline's in-process local backend.
        "CLINE_SESSION_BACKEND_MODE": "local",
        # Undocumented upstream test switch. In 3.0.62 its only effect is to
        # replace the PostHog feature-flag client (data.cline.bot) with a no-op
        # provider, so flags keep their built-in defaults. There is no
        # documented setting that disables this startup call.
        "E2E_TEST": "true",
    }
    command = [str(Path(__file__).resolve().parents[1] / "agent/node_modules/.bin/cline"), "--acp"]
    return command, child, base_url, model


def main() -> int:
    try:
        command, environ, base_url, model = prepare(dict(os.environ))
        # A disposable HOME keeps Cline's settings, session database and logs
        # writable by whichever unprivileged uid the runtime selects, and
        # isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-cline-home-"))
        settings = home / ".cline/data/settings"
        settings.mkdir(parents=True)
        (settings / "global-settings.json").write_text(json.dumps(GLOBAL_SETTINGS, indent=2))
        providers = settings / "providers.json"
        providers.write_text(json.dumps(provider_settings(base_url, model, environ["CLINE_PROVIDER"]), indent=2))
        providers.chmod(0o600)
        environ["HOME"] = str(home)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
