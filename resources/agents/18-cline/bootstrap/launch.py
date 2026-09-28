"""Map an OpenAI-compatible GLM profile onto Cline CLI's native ACP server."""
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
# Cline's built-in provider for Zhipu's OpenAI-compatible coding endpoint. The
# generic "openai-compatible" provider ignores CLINE_MODEL in ACP mode and
# silently falls back to its own default model.
PROVIDER = "zhipuai-coding-plan"
# Model IDs in the pinned Cline 3.0.62 catalog for this provider. An unknown ID is
# silently replaced by the provider default (glm-5.3-flash), so reject it here.
KNOWN_MODELS = frozenset({
    "glm-5.3-flash", "glm-5.3", "glm-5.3-highspeed", "glm-5.2", "glm-5.2-highspeed",
    "glm-5v-turbo", "glm-5.1", "glm-5-turbo", "glm-4.7", "glm-4.6v",
})
GLOBAL_SETTINGS = {
    # Cline sends OpenTelemetry to otel.cline.bot unless the user opts out, and
    # checks npm for updates; both are egress outside the admitted model route.
    "telemetryOptOut": True,
    "autoUpdateEnabled": False,
}


def provider_settings(base_url: str, model: str) -> dict:
    """Cline's providers.json with the base URL override; the key stays in env."""
    return {
        "version": 1,
        "providers": {
            PROVIDER: {
                "settings": {"provider": PROVIDER, "baseUrl": base_url, "model": model},
                "updatedAt": "2026-09-21T00:00:00.000Z",
                "tokenSource": "manual",
            }
        },
        "lastUsedProvider": PROVIDER,
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
    if model not in KNOWN_MODELS:
        raise ValueError(f"{MODEL_ENV}={model!r} is not in Cline's {PROVIDER} catalog")

    child = {
        **environ,
        # ACP session/new answers "Authentication required" unless CLINE_API_KEY
        # is set; Cline then uses it as the selected provider's key. Passing it
        # through the environment keeps it out of argv and out of files.
        "CLINE_API_KEY": key,
        "CLINE_PROVIDER": PROVIDER,
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
        providers.write_text(json.dumps(provider_settings(base_url, model), indent=2))
        providers.chmod(0o600)
        environ["HOME"] = str(home)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
