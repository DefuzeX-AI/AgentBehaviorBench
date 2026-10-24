"""Map the selected OpenAI-compatible model profile onto kimchi's native ACP server."""
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
PROVIDER = "abb"
KIMCHI = "/opt/kimchi/bin/kimchi"
# Kimchi multi-model roles; every role is pinned to the selected model so the
# orchestrator never delegates to a Kimchi-hosted default.
ROLES = ("orchestrator", "planner", "builder", "reviewer", "explorer", "researcher")
# Vendor settings that would enable the Kimchi gateway (model list, routing,
# web search, billing) or another hosted provider.
VENDOR_ENV = ("KIMCHI_API_KEY", "CASTAI_API_KEY", "OPENROUTER_API_KEY", "KIMCHI_BASE_URL")


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict[str, dict]]:
    """Return the kimchi ACP command, its environment and config files without secrets."""
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

    ref = f"{PROVIDER}/{model}"
    thinking = {"deepseek": "deepseek", "glm": "zai"}.get(environ.get("ABB_AGENT_MODEL_PROVIDER", ""))
    # Pi's models.json (kimchi's harness dir): a user-added provider that kimchi
    # keeps beside its own kimchi-dev block. "$NAME" is resolved from the
    # environment at request time, so the key never reaches disk or argv.
    models = {
        "providers": {
            PROVIDER: {
                "baseUrl": base_url,
                "api": "openai-completions",
                "apiKey": f"${KEY_ENV}",
                "compat": {"supportsDeveloperRole": False, **({"thinkingFormat": thinking} if thinking else {})},
                "models": [{"id": model, "reasoning": True, "contextWindow": 200000, "maxTokens": 32000}],
            }
        }
    }
    # ACP session/new does not choose a model, so the session starts on Pi's default.
    settings = {
        "defaultProvider": PROVIDER,
        "defaultModel": model,
        "modelRoles": {role: ref for role in ROLES},
        "quietStartup": True,
        "enableInstallTelemetry": False,
    }
    # kimchi's own ~/.config/kimchi/config.json: no Kimchi API key, telemetry off,
    # and first-run skill/migration prompts answered so startup stays headless.
    config = {"telemetry": {"enabled": False}, "skillPaths": [], "migrationState": "done"}
    child = {name: value for name, value in environ.items() if name not in VENDOR_ENV}
    child.update({
        # Telemetry (harness_launched, PostHog, OTLP) posts to Kimchi services.
        "KIMCHI_TELEMETRY_ENABLED": "0",
        # Self-update probe against GitHub releases (also skipped in ACP mode).
        "KIMCHI_NO_UPDATE_CHECK": "1",
        # Pi's catalog refresh, pi.dev version check and install telemetry.
        "PI_OFFLINE": "1",
        "PI_SKIP_VERSION_CHECK": "1",
        "PI_TELEMETRY": "0",
        # mem0's own PostHog telemetry in the memory extension.
        "MEM0_TELEMETRY": "false",
    })
    return [KIMCHI, "--mode", "acp"], child, {
        ".config/kimchi/harness/models.json": models,
        ".config/kimchi/harness/settings.json": settings,
        ".config/kimchi/config.json": config,
    }


def main() -> int:
    try:
        command, environ, files = prepare(dict(os.environ))
        # kimchi derives its config and agent dir from the home directory. A
        # disposable HOME keeps config, sessions and memory writable by whichever
        # unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-kimchi-home-"))
        for name, content in files.items():
            path = home / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(content, indent=2))
            path.chmod(0o600)
        environ["HOME"] = str(home)
        os.execve(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
