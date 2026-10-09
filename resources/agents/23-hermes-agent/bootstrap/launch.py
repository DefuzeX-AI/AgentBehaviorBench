"""Map an OpenAI-compatible GLM profile onto Hermes Agent's native ACP adapter."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
HERMES = "/opt/hermes/.venv/bin/hermes"
# Pinned tirith release installed at build time (agent/tirith.json).
TIRITH = "/opt/tirith/bin/tirith"
# Keyless OpenCode relays are listed in the ACP model picker by default and their
# catalog is fetched from opencode.ai at session start; exclude them.
EXCLUDED_PROVIDERS = ["opencode-free", "opencode-zen", "opencode-go"]


def config(base_url: str, model: str) -> dict:
    """Hermes config.yaml (JSON is valid YAML) for one Case."""
    return {
        # Hermes' built-in Z.AI/GLM provider speaks OpenAI chat completions.
        "model": {"provider": "zai", "default": model, "base_url": base_url},
        # The remote Nous model catalog and models.dev are startup metadata
        # fetches outside the evaluated model route. models.dev has no off
        # switch; a file:// URL makes requests fail locally (no connection
        # adapter) and Hermes falls back to its bundled data without any socket.
        "model_catalog": {"enabled": False, "excluded_providers": EXCLUDED_PROVIDERS},
        "models_dev": {"url": "file:///nonexistent/models.dev-disabled.json"},
        # Background model calls started after a turn (session titles, the
        # self-improvement review fork) are cut when the one-shot worker closes ACP.
        "auxiliary": {
            "title_generation": {"enabled": False},
            "background_review": {"enabled": False},
        },
        "curator": {"enabled": False},
        "updates": {"check": False},
        # Hermes scans every terminal command with tirith and, when the binary is
        # missing, downloads it from GitHub on first use. An explicit path is
        # authoritative upstream (never auto-downloaded), so the scan stays on.
        "security": {"tirith_enabled": True, "tirith_path": TIRITH},
    }


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str], dict]:
    """Return the Hermes ACP command, environment and config without persisting secrets."""
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

    # Hermes' Z.AI provider reads GLM_API_KEY natively; an explicit GLM_BASE_URL
    # also skips its endpoint auto-detection probes. The key never enters argv.
    child = {
        **environ,
        KEY_ENV: key,
        "GLM_BASE_URL": base_url,
        # Keep the venv sealed as upstream's image does (Dockerfile:430), but let optional
        # backends install on demand into a writable target (upstream Dockerfile:443;
        # tools/lazy_deps.py:325-339). PyPI is reachable through the egress observer.
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "HERMES_LAZY_INSTALL_TARGET": os.path.join(tempfile.gettempdir(), "abb-hermes-lazy"),
        # tirith otherwise refreshes its threat database from GitHub while
        # scanning; offline mode keeps the bundled rules and makes no connection.
        "TIRITH_OFFLINE": "1",
        # Attach Hermes' browser tools to the per-Case Chromium started in main()
        # (upstream tools/browser_tool_cdp.py:51-60).
        "BROWSER_CDP_URL": "http://127.0.0.1:9222",
    }
    return [HERMES, "acp"], child, config(base_url, model)


def main() -> int:
    try:
        command, environ, settings = prepare(dict(os.environ))
        # A disposable HOME keeps Hermes' state (config, sessions, SQLite, logs)
        # writable by whichever unprivileged uid the runtime selects, per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-hermes-home-"))
        hermes_home = home / ".hermes"
        hermes_home.mkdir()
        (hermes_home / "config.yaml").write_text(json.dumps(settings, indent=2))
        environ.update({
            "HOME": str(home),
            "HERMES_HOME": str(hermes_home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_CACHE_HOME": str(home / ".cache"),
        })
        # One headless Chromium per Case on a fixed CDP port (agent-browser's own launch
        # picks a random port, which cannot be declared: the runtime redirects loopback
        # TCP too). The loopback tool route 127.0.0.1:9222 in network/rules.toml admits
        # the CDP traffic; the loop restarts Chromium if Hermes' cleanup closes it.
        with open(home / "abb-chromium.log", "ab") as chromium_log:
            subprocess.Popen(
                ["sh", "-c", 'while :; do /usr/local/bin/abb-chromium --headless=new --remote-debugging-port=9222 '
                             '--user-data-dir="$HOME/.abb-chromium" about:blank; sleep 1; done'],
                stdin=subprocess.DEVNULL, stdout=chromium_log, stderr=chromium_log, start_new_session=True,
                env={k: v for k, v in environ.items() if k != KEY_ENV})
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
