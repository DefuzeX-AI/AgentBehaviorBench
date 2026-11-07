"""Map the selected OpenAI-compatible model profile onto Moltis's native ACP server."""
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
MOLTIS = "/opt/moltis/bin/moltis"
# Moltis names OpenAI-compatible endpoints with a "custom-" prefix.
PROVIDER = "custom-abb"
# Provider credentials and overrides Moltis would otherwise pick up for its
# built-in providers, embeddings, web search or remote sandboxes.
FOREIGN_KEYS = (
    "OPENAI_API_KEY", "OPENAI_BASE_URL", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "GOOGLE_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "MISTRAL_API_KEY",
    "GROQ_API_KEY", "XAI_API_KEY", "MOONSHOT_API_KEY", "MINIMAX_API_KEY",
    "ZAI_API_KEY", "DASHSCOPE_API_KEY", "VOYAGE_API_KEY", "BRAVE_API_KEY",
    "PERPLEXITY_API_KEY", "TAVILY_API_KEY", "FIRECRAWL_API_KEY", "ELEVENLABS_API_KEY",
    "VERCEL_TOKEN", "DAYTONA_API_KEY", "MOLTIS_CONFIG_DIR", "MOLTIS_DATA_DIR",
)


def _toml_str(value: str) -> str:
    # JSON string escaping is valid TOML basic-string syntax for these values.
    return json.dumps(value)


def render_config(base_url: str, model: str) -> str:
    """Return the moltis.toml that offers only the selected model."""
    return "\n".join(
        [
            "[providers]",
            f"offered = [{_toml_str(PROVIDER)}]",
            "",
            f"[providers.{PROVIDER}]",
            "enabled = true",
            # Moltis substitutes ${...} from the environment when it loads the
            # file, so the key itself is never written here.
            f'api_key = "${{{KEY_ENV}}}"',
            f"base_url = {_toml_str(base_url)}",
            f"models = [{_toml_str(model)}]",
            # Chat Completions posts to <base_url>/chat/completions, the admitted
            # route; the model list is fixed, so no catalog request is made.
            'wire_api = "chat-completions"',
            "fetch_models = false",
            "",
            # No container runtime exists inside the Agent image, so "auto" falls
            # back to the restricted-host backend, which confines file tools to
            # the data directory and /tmp and rejects every write to the session
            # cwd. The Agent container is the isolation boundary here; "off"
            # runs tools directly in it, in the session cwd.
            "[tools.exec.sandbox]",
            'mode = "off"',
            "",
            # `moltis acp` does not route session/request_permission through its
            # tool gate (docs/src/acp-server.md), so the default "on-miss" holds
            # every command outside the safe-bin list for the 120 s approval
            # timeout and then denies it. "off" is the documented headless value:
            # dangerous patterns are still denied (crates/tools/src/approval.rs).
            "[tools.exec]",
            'approval_mode = "off"',
            "",
        ]
    )


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


def prepare(environ: dict[str, str], root: Path, base_url: str, model: str) -> tuple[list[str], dict[str, str]]:
    """Write the disposable Moltis directories under root and return command and environment."""
    config_dir = root / "config"
    data_dir = root / "data"
    for path in (config_dir, data_dir):
        path.mkdir(parents=True, exist_ok=True)
    (config_dir / "moltis.toml").write_text(render_config(base_url, model))

    child = dict(environ)
    for name in FOREIGN_KEYS:
        child.pop(name, None)
    child.update({
        # Config, databases, sessions, memory and logs stay out of the Case
        # workspace and writable by whichever unprivileged uid the runtime uses.
        "XDG_CONFIG_HOME": str(root / "xdg-config"),
        "XDG_DATA_HOME": str(root / "xdg-data"),
        "XDG_CACHE_HOME": str(root / "xdg-cache"),
        "USER": environ.get("USER") or "agent",
    })
    command = [MOLTIS, "acp", "--config-dir", str(config_dir), "--data-dir", str(data_dir)]
    return command, child


def main() -> int:
    try:
        environ = dict(os.environ)
        base_url, model = validated(environ)
        root = Path(tempfile.mkdtemp(prefix="abb-moltis-"))
        command, child = prepare(environ, root, base_url, model)
        os.execve(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
