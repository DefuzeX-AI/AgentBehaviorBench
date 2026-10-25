"""ABB outer launcher for QwenPaw's native ACP server (modelled on the other ACP unit launchers).

Maps ABB's shared model selection (ABB_AGENT_MODEL_API_KEY / ABB_AGENT_MODEL_BASE_URL / ABB_AGENT_MODEL;
ABB_AGENT_MODEL_PROVIDER is informational: every shared profile is an OpenAI-compatible Chat Completions model)
onto QwenPaw's documented headless provider `qwenpaw acp --runtime-provider openai-env`
(src/qwenpaw/cli/acp_cmd.py, agents/acp/runtime_provider.py): OPENAI_BASE_URL, OPENAI_API_KEY, OPENAI_MODEL.
QwenPaw keeps config, agent workspace (AGENTS.md, memory) and secrets under QWENPAW_WORKING_DIR (default ~/.qwenpaw);
the launcher points HOME and QWENPAW_WORKING_DIR at a disposable per-Case directory. The project directory is the
ACP session cwd sent by the client (QwenPaw records it as the session's project dir).
Standard library only (runs under the image's system python).
"""
from __future__ import annotations

import os
import sys
import tempfile
from urllib.parse import urlsplit

KEY_ENV, BASE_URL_ENV, MODEL_ENV = "ABB_AGENT_MODEL_API_KEY", "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL"
QWENPAW_BIN = os.environ.get("ABB_QWENPAW_BIN", "/opt/qwenpaw-venv/bin/qwenpaw")


def prepare(environ):
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    for name, value in ((KEY_ENV, key), (BASE_URL_ENV, base_url), (MODEL_ENV, model)):
        if not value:
            raise ValueError(f"{name} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    child = {**environ, "OPENAI_BASE_URL": base_url, "OPENAI_API_KEY": key, "OPENAI_MODEL": model}
    child.pop("OPENAI_API_BASE", None)
    return [QWENPAW_BIN, "acp", "--runtime-provider", "openai-env"], child


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        home = tempfile.mkdtemp(prefix="abb-qwenpaw-home-")
        environ["HOME"] = home
        environ["QWENPAW_WORKING_DIR"] = os.path.join(home, ".qwenpaw")
        environ["QWENPAW_SECRET_DIR"] = os.path.join(home, ".qwenpaw.secret")
        environ["QWENPAW_BACKUP_DIR"] = os.path.join(home, ".qwenpaw.backups")
        for var in ("XDG_CONFIG_HOME", "XDG_DATA_HOME", "XDG_CACHE_HOME", "XDG_STATE_HOME"):
            environ.pop(var, None)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError) as exc:
        print(str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
