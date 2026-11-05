"""Map the selected OpenAI-compatible model profile onto Portable Hermes Agent's ACP adapter.

Portable Hermes Agent 0.20.6 (tag v1.4.17) resolves its model endpoint from
config.yaml, not from OPENAI_BASE_URL: hermes_cli/runtime_provider.py:1392-1393
states the env var "is no longer consulted - config.yaml is the single source of
truth for endpoint URLs", and :1447-1458 host-gates OPENAI_API_KEY to
openai.com/openai.azure.com so an OpenRouter/DeepSeek/GLM endpoint would resolve
to no credential at all. This launcher therefore writes the endpoint into the
per-Case config.yaml and pins the wire shape to chat_completions.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
HERMES = "/opt/hermes/.venv/bin/hermes"
# Pinned tirith release installed at build time (agent/tirith.json).
TIRITH = "/opt/tirith/bin/tirith"
# Keyless OpenCode relays are listed in the ACP model picker by default and their
# catalog is fetched from opencode.ai at session start; exclude them.
EXCLUDED_PROVIDERS = ["opencode-free", "opencode-zen", "opencode-go"]


def config(base_url: str, model: str) -> dict:
    """Hermes config.yaml (JSON is valid YAML) for one Case."""
    return {
        # `custom` is the documented id for "any other OpenAI-compatible endpoint"
        # (cli-config.yaml.example:73-74). Bare `custom` is the one provider whose
        # configured base_url is trusted unconditionally
        # (_config_base_url_trustworthy_for_bare_custom, runtime_provider.py:110-111),
        # which also makes the config-supplied api_key usable (:1449).
        "model": {
            "provider": "custom",
            "default": model,
            "base_url": base_url,
            # A ${VAR} reference, expanded from the environment by
            # hermes_cli/config.py:_expand_env_vars (:2778-2792). The credential
            # therefore never lands in a file as plaintext.
            "api_key": "${" + KEY_ENV + "}",
            # ABB admits exactly POST <selected-base>/chat/completions
            # (agentbench/runtime/interception/native_model.py:82-92,107). Pin the
            # transport so it cannot fall back to a provider overlay's
            # codex_responses shape, which would hit /responses as undeclared
            # egress. Honored for bare custom by _resolve_plain_custom_api_mode
            # (runtime_provider.py:221-232).
            "api_mode": "chat_completions",
        },
        # The remote Nous model catalog and models.dev are startup metadata
        # fetches outside the evaluated model route. models.dev has no off
        # switch; a file:// URL makes requests fail locally (no connection
        # adapter) and Hermes falls back to its bundled data without any socket.
        "model_catalog": {"enabled": False, "excluded_providers": EXCLUDED_PROVIDERS},
        "models_dev": {"url": "file:///nonexistent/models.dev-disabled.json"},
        # Background model calls started after a turn (session titles, the
        # self-improvement review fork) are cut when the one-shot worker closes ACP.
        # Both keys exist in this release's DEFAULT_CONFIG (config_defaults.py:1212,
        # :1334) and background_review.py:281 reads the enabled flag.
        "auxiliary": {
            "title_generation": {"enabled": False},
            "background_review": {"enabled": False},
        },
        "curator": {"enabled": False},
        # NOTE: no `updates.check` here. That key does not exist in 0.20.6; update
        # checks are the `hermes update` CLI and the `hermes_update` toolset, which
        # is not part of the `hermes-acp` toolset exposed over ACP (toolsets.py:532-550).
        # Hermes scans every terminal command with tirith and, when the binary is
        # missing, downloads it from GitHub on first use. An explicit path is
        # authoritative upstream (never auto-downloaded: _is_explicit_path ->
        # _resolve_tirith_path, tirith_security.py:488-503), so the scan stays on.
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

    child = {
        **environ,
        # config.yaml is authoritative for the endpoint (see module docstring);
        # the key stays in the environment because the config only references it.
        KEY_ENV: key,
        # Keep the venv sealed as upstream's image does (Dockerfile:388), but let
        # optional backends install on demand into a writable target
        # (tools/lazy_deps.py:537,1064). PyPI is reachable through the egress observer.
        "HERMES_DISABLE_LAZY_INSTALLS": "1",
        "HERMES_LAZY_INSTALL_TARGET": os.path.join(tempfile.gettempdir(), "abb-hermes-lazy"),
        # tirith otherwise refreshes its threat database while scanning; offline
        # mode keeps the bundled rules and makes no connection.
        "TIRITH_OFFLINE": "1",
        # Attach Hermes' browser tools to the per-Case Chromium started in main()
        # (tools/browser_tool.py:567 reads BROWSER_CDP_URL).
        "BROWSER_CDP_URL": "http://127.0.0.1:9222",
        # No MCP servers are configured for evaluation; skip the startup discovery
        # so it cannot reach an undeclared host (acp_adapter/entry.py:260).
        "HERMES_ACP_SKIP_CONFIGURED_MCP": "1",
        # Portable Hermes bootstraps a Node.js runtime for its GUI/TUI surfaces.
        # Neither is used over ACP, and the download would be undeclared egress
        # (hermes_cli/main.py:2392-2396).
        "HERMES_SKIP_NODE_BOOTSTRAP": "1",
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
