"""Map the selected OpenAI-compatible model profile onto open-code-review's native ACP adapter (ocr-acp).

1. Review model: OCR's documented environment endpoint (internal/llm resolver): OCR_LLM_URL, OCR_LLM_TOKEN,
   OCR_LLM_MODEL, OCR_LLM_PROTOCOL=openai.
2. Natural-language intent parser (acp/README "Parsing LLM configuration"): OCR_ACP_PARSER_PROVIDER=openai,
   OCR_ACP_PARSER_MODEL, OCR_ACP_PARSER_BASE_URL, OCR_ACP_PARSER_API_KEY. Slash commands do not need it.
3. Workspace: /review needs a Git repository. ABB fixtures cannot contain .git, so when the workspace is not a
   repository yet the launcher runs `git init` and commits the fixture once as a baseline (like a developer's
   checkout). Nothing else is written to the workspace.
4. Disposable HOME (OCR keeps config and sessions under ~/.opencodereview), then exec ocr-acp. ACP messages are
   passed through unchanged: the launcher is not on the stdio path.
Standard library only.
"""
from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
OCR_ACP_BIN = "/opt/agent/bin/ocr-acp"
OCR_BIN = "/opt/agent/bin/opencodereview"
GIT_IDENTITY = {"GIT_AUTHOR_NAME": "dev", "GIT_AUTHOR_EMAIL": "dev@example.com",
                "GIT_COMMITTER_NAME": "dev", "GIT_COMMITTER_EMAIL": "dev@example.com"}


def prepare(environ: dict[str, str]) -> tuple[list[str], dict[str, str]]:
    key = environ.get(KEY_ENV, "").strip()
    base_url = environ.get(BASE_URL_ENV, "").strip().rstrip("/")
    model = environ.get(MODEL_ENV, "").strip()
    for name, value in ((KEY_ENV, key), (BASE_URL_ENV, base_url), (MODEL_ENV, model)):
        if not value:
            raise ValueError(f"{name} is required")
    parsed = urlsplit(base_url)
    if parsed.scheme != "https" or not parsed.hostname or parsed.query or parsed.fragment:
        raise ValueError(f"{BASE_URL_ENV} must be an HTTPS URL without query or fragment")
    child = {k: v for k, v in environ.items() if not k.startswith(("ABB_AGENT_MODEL", "OCR_"))}
    child.update({
        "OCR_LLM_URL": base_url, "OCR_LLM_TOKEN": key, "OCR_LLM_MODEL": model, "OCR_LLM_PROTOCOL": "openai",
        "OCR_ACP_PARSER_PROVIDER": "openai", "OCR_ACP_PARSER_MODEL": model,
        "OCR_ACP_PARSER_BASE_URL": base_url, "OCR_ACP_PARSER_API_KEY": key,
        "OCR_NO_UPDATE": "1", "OCR_ENABLE_TELEMETRY": "false",
    })
    return [OCR_ACP_BIN, "--ocr-binary", OCR_BIN], child


def ensure_repository(workspace: Path, environ: dict[str, str]) -> None:
    if (workspace / ".git").exists():
        return
    env = {k: v for k, v in environ.items() if not k.startswith(("ABB_AGENT_MODEL", "OCR_"))}
    env.update(GIT_IDENTITY)
    for args in (["init", "-q", "-b", "main"], ["add", "-A"],
                 ["commit", "-q", "--allow-empty", "-m", "Workspace baseline"]):
        subprocess.run(["git", *args], cwd=workspace, env=env, check=True,
                       stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr)


def main() -> int:
    try:
        command, environ = prepare(dict(os.environ))
        environ["HOME"] = tempfile.mkdtemp(prefix="abb-ocr-home-")
        ensure_repository(Path.cwd(), environ)
        os.execvpe(command[0], command, environ)
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]"), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
