"""Map an OpenAI-compatible GLM profile onto Mastra Code's custom provider and start `mastracode --acp`."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
PROVIDER_NAME = "abb-glm"
MASTRACODE_BIN = Path(__file__).resolve().parents[1] / "agent/node_modules/.bin/mastracode"
# Mastra Code's ACP server offers these modes (mastracode/sdk/src/acp/index.ts).
MODES = ("build", "plan", "fast")


def settings_document(base_url: str, model: str, key: str) -> dict[str, object]:
    """Return a settings.json that routes every Mastra Code model role to one custom provider.

    Mastra Code reads a custom provider's credential only from settings.json (or
    its auth store); there is no environment-variable indirection. Inside ABB
    the value is the interceptor's surrogate credential, and the file lives in a
    disposable per-Case directory with mode 0600.
    """
    model_id = f"{PROVIDER_NAME}/{model}"
    return {
        # Mark first-run onboarding as done so no pack picker or login is needed.
        "onboarding": {
            "completedAt": "1970-01-01T00:00:00.000Z",
            "skippedAt": None,
            "version": 1,
            "modePackId": "custom",
            "omPackId": "custom",
            "quietModePreferenceSelected": True,
        },
        "models": {
            "activeModelPackId": None,
            "modeDefaults": {mode: model_id for mode in MODES},
            "activeOmPackId": None,
            # Observational memory (observer/reflector) and /goal judging would
            # otherwise default to a built-in pack on another provider.
            "omModelOverride": model_id,
            "observerModelOverride": model_id,
            "reflectorModelOverride": model_id,
            "goalJudgeModel": model_id,
            "subagentModels": {},
        },
        "customProviders": [
            {"name": PROVIDER_NAME, "url": base_url, "apiKey": key, "models": [model]},
        ],
    }


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Return the Mastra Code ACP command, its environment and settings.json content."""
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

    child = {
        **environ,
        "HOME": str(home),
        # settings.json, auth.json, the libsql thread store and vector store.
        "MASTRA_APP_DATA_DIR": str(home / "mastracode"),
        # PostHog product analytics would be undeclared egress.
        "MASTRA_TELEMETRY_DISABLED": "1",
        # Skips Mastra's provider-registry background sync (models.dev/Netlify).
        "MASTRA_OFFLINE": "1",
    }
    for var, sub in (("XDG_CONFIG_HOME", ".config"), ("XDG_DATA_HOME", ".local/share"),
                     ("XDG_STATE_HOME", ".local/state"), ("XDG_CACHE_HOME", ".cache")):
        child[var] = str(home / sub)
    return [str(MASTRACODE_BIN), "--acp"], child, settings_document(base_url, model, key)


def main() -> int:
    try:
        # A disposable HOME keeps Mastra Code's settings, thread database and
        # locks writable by whichever unprivileged uid the runtime selects, and
        # isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-mastracode-home-"))
        command, environ, settings = prepare(dict(os.environ), home)
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
            Path(environ[var]).mkdir(parents=True, exist_ok=True)
        app_dir = Path(environ["MASTRA_APP_DATA_DIR"])
        app_dir.mkdir(mode=0o700)
        fd = os.open(app_dir / "settings.json", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(settings, handle, indent=2)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    return relay(command, environ)


def relay(command: list[str], environ: dict[str, str]) -> int:
    """Run Mastra Code with inherited stdin and keep its stdout pure JSON-RPC.

    On exit Mastra Code's terminal library writes terminal reset escape
    sequences (e.g. bracketed-paste off, cursor show) to stdout after the last
    JSON-RPC message; the ACP client cannot parse them. Lines that are not JSON
    objects are moved to stderr unchanged; every JSON line passes through as is.
    """
    child = subprocess.Popen(command, env=environ, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))
    out, err = sys.stdout.buffer, sys.stderr.buffer
    try:
        for line in child.stdout:
            target = out if line.lstrip().startswith(b"{") else err
            target.write(line)
            target.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
