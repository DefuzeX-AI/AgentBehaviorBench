"""Map a DashScope Qwen profile onto Qwen Code's native ACP server."""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "DASHSCOPE_API_KEY"
BASE_URL_ENV = "QWEN_API_BASE_URL"
MODEL_ENV = "QWEN_MODEL"
SETTINGS = {
    "privacy": {"usageStatisticsEnabled": False},
    "telemetry": {"enabled": False},
    "general": {"enableAutoUpdate": False},
    # Background memory extraction starts a second model call after each turn;
    # the one-shot worker closes ACP before it finishes and the trace is cut.
    "memory": {"enableManagedAutoMemory": False, "enableManagedAutoDream": False},
}


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    """Return the Qwen Code ACP command and environment without persisting secrets."""
    key = environ.get(KEY_ENV, "").strip()
    base_url = (environ.get(BASE_URL_ENV, "").strip() or "https://dashscope.aliyuncs.com/compatible-mode/v1").rstrip("/")
    model = environ.get(MODEL_ENV, "").strip() or "qwen3-coder-plus"
    if not key:
        raise ValueError(f"{KEY_ENV} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")

    # Qwen Code's native OpenAI auth reads these variables; the key never
    # appears in argv, where process listings and evidence could capture it.
    child = {
        **environ,
        "OPENAI_API_KEY": key,
        "OPENAI_BASE_URL": base_url,
        "OPENAI_MODEL": model,
        # Usage statistics go to a third-party RUM endpoint outside the
        # evaluated model route; keep them off so egress stays allowlisted.
        "QWEN_USAGE_STATISTICS_ENABLED": "false",
    }
    command = [str(Path(__file__).resolve().parents[1] / "agent/node_modules/.bin/qwen"), "--acp", "--auth-type", "openai", "--model", model]
    return command, child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        # A disposable HOME keeps Qwen's settings and session files writable by
        # whichever unprivileged uid the runtime selects, and isolated per Case.
        home = Path(tempfile.mkdtemp(prefix="abb-qwen-home-"))
        (home / ".qwen").mkdir()
        (home / ".qwen/settings.json").write_text(json.dumps(SETTINGS, indent=2))
        environ["HOME"] = str(home)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
