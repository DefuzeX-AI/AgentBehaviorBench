"""Map the selected OpenAI-compatible model profile onto Mini-Agent's config and start its ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
MINI_AGENT_PYTHON = "/opt/mini-agent/bin/python"
# read_file counts tokens with tiktoken's cl100k_base, which tiktoken otherwise downloads
# from openaipublic.blob.core.windows.net on first use; the Dockerfile caches it here.
TIKTOKEN_CACHE = "/opt/mini-agent-tiktoken"
ACP_SERVER = Path(__file__).resolve().with_name("acp_server.py")
# Pinned upstream templates that scripts/setup-config.sh copies; the wheel omits them.
SOURCE_CONFIG = Path(__file__).resolve().parents[1] / "agent/mini_agent/config"


def config_document(key: str, base_url: str, model: str) -> dict[str, object]:
    """Return config.yaml content: upstream's config-example.yaml with the model fields set.

    ``provider: openai`` selects Mini-Agent's own OpenAI client, and a non-MiniMax
    ``api_base`` is used as-is (llm/llm_wrapper.py), so requests go to
    ``<base_url>/chat/completions``. The remaining values are those of the pinned
    config-example.yaml.
    """
    return {
        "api_key": key,
        "api_base": base_url,
        "model": model,
        "provider": "openai",
        "retry": {"enabled": True, "max_retries": 3, "initial_delay": 1.0,
                  "max_delay": 60.0, "exponential_base": 2.0},
        "max_steps": 100,
        "workspace_dir": "./workspace",
        "system_prompt_path": "system_prompt.md",
        "tools": {
            "enable_file_tools": True, "enable_bash": True, "enable_note": True,
            "enable_skills": True, "skills_dir": "./skills",
            "enable_mcp": True, "mcp_config_path": "mcp.json",
            "mcp": {"connect_timeout": 10.0, "execute_timeout": 60.0, "sse_read_timeout": 120.0},
        },
    }


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], dict[str, object]]:
    """Return the ACP server command, its environment and the config.yaml document."""
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

    # Mini-Agent reads the key only from config.yaml; its bash tool's children do not
    # need it in their environment.
    child = {k: v for k, v in environ.items() if k != KEY_ENV}
    child["HOME"] = str(home)
    child["TIKTOKEN_CACHE_DIR"] = TIKTOKEN_CACHE
    return [MINI_AGENT_PYTHON, str(ACP_SERVER)], child, config_document(key, base_url, model)


def write_config(home: Path, document: dict[str, object]) -> None:
    """Reproduce scripts/setup-config.sh under ``~/.mini-agent/config`` from pinned files.

    config.yaml is JSON (a YAML subset) created 0600 inside the per-Case HOME. The
    example MCP file declares every server disabled, as in the documented setup.
    """
    config_dir = home / ".mini-agent" / "config"
    config_dir.mkdir(parents=True)
    descriptor = os.open(config_dir / "config.yaml", os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
        json.dump(document, handle, indent=2)
    shutil.copyfile(SOURCE_CONFIG / "mcp-example.json", config_dir / "mcp.json")
    shutil.copyfile(SOURCE_CONFIG / "system_prompt.md", config_dir / "system_prompt.md")


def main() -> int:
    try:
        # A disposable HOME keeps config, logs (~/.mini-agent/log) and caches writable
        # by whichever unprivileged uid the runtime selects, and isolates Cases.
        home = Path(tempfile.mkdtemp(prefix="abb-mini-agent-home-"))
        command, environ, document = prepare(dict(os.environ), home)
        write_config(home, document)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1
    sys.stdout.flush()
    sys.stderr.flush()
    # stdin/stdout are the ACP stdio channel; the Mini-Agent process takes them over.
    os.execve(command[0], command, environ)
    return 1  # pragma: no cover - execve does not return


if __name__ == "__main__":
    raise SystemExit(main())
