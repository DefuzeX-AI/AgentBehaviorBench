"""Launch Whip's native ACP adapter and bound its daemon to this Case."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit

BINARY = "/usr/local/bin/whipcode"
KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
FOREIGN_KEYS = (
    "OPENAI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY", "ANTHROPIC_API_KEY",
    "GEMINI_API_KEY", "GOOGLE_API_KEY", "GLM_API_KEY", "XAI_API_KEY",
    "WHIPCODE_HOME", "WHIPCODE_NETWORK", "WHIPCODE_LISTEN",
)


def prepare(environ: dict[str, str], root: Path) -> dict[str, str]:
    """Use native provider configuration without serializing the credential."""
    required = (KEY_ENV, "ABB_AGENT_MODEL_BASE_URL", "ABB_AGENT_MODEL")
    if any(not environ.get(name, "").strip() for name in required):
        raise ValueError("ABB_AGENT_MODEL_API_KEY, ABB_AGENT_MODEL_BASE_URL and ABB_AGENT_MODEL are required")
    base = environ["ABB_AGENT_MODEL_BASE_URL"].strip().rstrip("/")
    parsed = urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("ABB_AGENT_MODEL_BASE_URL must be an HTTPS endpoint without credentials, query or fragment")
    home = root / "home"
    config = home / ".whipcode"
    config.mkdir(parents=True, mode=0o700)
    document = {
        "defaultModel": "abb", "defaultProvider": "abb",
        "providers": {"abb": {"baseUrl": base, "api": "openai-completions", "apiKeyEnv": KEY_ENV}},
        "models": {"abb": {"id": environ["ABB_AGENT_MODEL"], "providers": ["abb"], "context": 65536, "maxOut": 8192}},
    }
    (config / "config.json").write_text(json.dumps(document, indent=2) + "\n")
    (config / "config.json").chmod(0o600)
    child = {k: v for k, v in environ.items() if k not in FOREIGN_KEYS}
    child.update(HOME=str(home), WHIPCODE_HOME=str(config), WHIPCODE_NETWORK="0")
    return child


def main() -> int:
    # Native daemon state is outside the Case workspace and unique to this ACP session.
    with tempfile.TemporaryDirectory(prefix="abb-whip-") as temporary:
        try:
            child_env = prepare(dict(os.environ), Path(temporary))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        started = subprocess.run([BINARY, "daemon", "start"], env=child_env,
                                 stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr)
        if started.returncode:
            return started.returncode
        process = None
        try:
            process = subprocess.Popen([BINARY, "acp", "-m", "abb", "-p", "abb"], env=child_env)
            signal.signal(signal.SIGTERM, lambda *_: process.terminate())
            signal.signal(signal.SIGINT, lambda *_: process.send_signal(signal.SIGINT))
            return process.wait()
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            subprocess.run([BINARY, "daemon", "stop", "--timeout", "10s", "--force"], env=child_env,
                           stdin=subprocess.DEVNULL, stdout=sys.stderr, stderr=sys.stderr, timeout=20)


if __name__ == "__main__":
    raise SystemExit(main())
