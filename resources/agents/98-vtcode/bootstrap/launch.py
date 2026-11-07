"""Map the selected OpenAI-compatible model profile onto VT Code's native ACP server."""
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
VTCODE = "/opt/vtcode/bin/vtcode"
PROVIDER = "abb"
# Provider credentials VT Code would otherwise pick up for its built-in providers.
FOREIGN_KEYS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "XAI_API_KEY", "ZAI_API_KEY",
    "MOONSHOT_API_KEY", "MINIMAX_API_KEY", "OLLAMA_API_KEY", "HF_TOKEN",
)


def _toml_str(value: str) -> str:
    # JSON string escaping is valid TOML basic-string syntax for these values.
    return json.dumps(value)


def render_config(base_url: str, model: str) -> str:
    """Return the vtcode.toml that selects the configured model and switches off extras."""
    return "\n".join(
        [
            "[agent]",
            f"provider = {_toml_str(PROVIDER)}",
            f"default_model = {_toml_str(model)}",
            # VT Code reads the key from this variable; it is never written here.
            f"api_key_env = {_toml_str(KEY_ENV)}",
            "",
            "[agent.persistent_memory]",
            "enabled = false",
            "",
            "[agent.checkpointing]",
            "enabled = false",
            "",
            "[features]",
            "memories = false",
            "",
            "[telemetry]",
            "atif_enabled = false",
            "dashboards_enabled = false",
            "perf_events = false",
            "",
            # The ACP bridge asks the client (session/request_permission) before
            # apply_patch runs, but the release then re-checks the internal tool
            # policy, whose default "prompt" has no handler under ACP and denies
            # every edit. "allow" leaves the ACP permission request as the gate.
            "[tools.policies]",
            'apply_patch = "allow"',
            "",
            "[acp]",
            "enabled = true",
            "",
            "[acp.zed]",
            "enabled = true",
            'transport = "stdio"',
            "",
            "[[custom_providers]]",
            f"name = {_toml_str(PROVIDER)}",
            'display_name = "ABB selected model"',
            f"base_url = {_toml_str(base_url)}",
            f"api_key_env = {_toml_str(KEY_ENV)}",
            f"model = {_toml_str(model)}",
            # Chat Completions posts to <base_url>/chat/completions, the admitted route.
            'api_format = "openai-chat"',
            "supports_tools = true",
            "",
        ]
    )


# The release checks GitHub for new versions on a schedule; 0 disables it.
UPDATE_CONFIG = "check_interval_hours = 0\n"


def validated(environ: dict[str, str]) -> tuple[str, str]:
    """Return the base URL and model after checking the three model variables."""
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
    return base_url, model


def prepare_home(environ: dict[str, str], root: Path, base_url: str, model: str) -> tuple[list[str], dict[str, str]]:
    """Write the disposable VT Code directories under root and return command and environment."""
    dirs = {name: root / name for name in ("config", "data", "state", "cache", "legacy", "bin")}
    for path in dirs.values():
        path.mkdir(parents=True, exist_ok=True)
    config_dir = dirs["config"] / "vtcode"
    config_dir.mkdir(exist_ok=True)
    config = config_dir / "vtcode.toml"
    config.write_text(render_config(base_url, model))
    (config_dir / "update.toml").write_text(UPDATE_CONFIG)

    child = dict(environ)
    for name in FOREIGN_KEYS:
        child.pop(name, None)
    child.update({
        # Keep config, sessions, trust records and caches out of the Case
        # workspace and writable by whichever unprivileged uid the runtime uses.
        "XDG_CONFIG_HOME": str(dirs["config"]),
        "XDG_DATA_HOME": str(dirs["data"]),
        "XDG_STATE_HOME": str(dirs["state"]),
        "XDG_CACHE_HOME": str(dirs["cache"]),
        "XDG_BIN_HOME": str(dirs["bin"]),
        "VTCODE_HOME": str(dirs["legacy"]),
        # The explicit file replaces the workspace vtcode.toml layer, so a Case
        # cannot redirect the provider by writing one into the workspace.
        "VTCODE_CONFIG_PATH": str(config),
        "USER": environ.get("USER") or "agent",
    })
    return [VTCODE, "acp", "standard"], child


def main() -> int:
    try:
        environ = dict(os.environ)
        base_url, model = validated(environ)
        root = Path(tempfile.mkdtemp(prefix="abb-vtcode-"))
        command, child = prepare_home(environ, root, base_url, model)
        os.execve(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
