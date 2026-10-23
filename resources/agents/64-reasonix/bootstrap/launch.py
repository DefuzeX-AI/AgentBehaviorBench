"""Map the selected OpenAI-compatible model profile onto Reasonix's native ACP server.

`reasonix acp` speaks spec ACP on stdio: stdout carries JSON-RPC only and every
diagnostic goes to stderr. Reasonix resolves a provider's credential from
`<Reasonix home>/.env` alone — the process environment is never consulted — and
the provider list from `<Reasonix home>/config.toml`. This launcher therefore
writes both files into a disposable home for every Case before starting the
binary. The key itself reaches the child only as an environment variable that
`.env` names, so it is never written into `config.toml`.
"""
from __future__ import annotations

import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import json
from urllib.parse import urlsplit


KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
REASONIX_BIN = "/opt/reasonix/bin/reasonix"
PROVIDER_ID = "abb"
# Conservative deployment budget; do not reuse the previous provider catalog.
DEFAULT_CONTEXT_LIMIT = 128_000


def toml_string(value: str) -> str:
    """Return a TOML basic string literal."""
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def config_toml(base_url: str, model: str) -> str:
    """Return Reasonix's global config.toml for one static OpenAI-compatible provider.

    `models` is a static one-entry list. Reasonix otherwise discovers models over
    `GET <base>/models`, which is outside the admitted model route. Nothing else is
    declared: every other upstream default (tool set, telemetry policy, sandbox
    posture) is left exactly as the pinned release ships it, and no tool is
    disabled to fit one provider.
    """
    return "\n".join([
        "config_version = 1",
        # Reasonix resolves "provider/model"; the provider entry below carries the
        # same default, so the pair stays consistent when the model id contains a
        # slash of its own.
        f"default_model = {toml_string(PROVIDER_ID + '/' + model)}",
        "",
        "[[providers]]",
        f"name           = {toml_string(PROVIDER_ID)}",
        'kind           = "openai"',
        f"base_url       = {toml_string(base_url)}",
        f"models         = [{toml_string(model)}]",
        f"default        = {toml_string(model)}",
        f"api_key_env    = {toml_string(KEY_ENV)}",
        f"context_window = {DEFAULT_CONTEXT_LIMIT}",
        "",
    ])


def credentials_env(key: str) -> str:
    """Return the `<Reasonix home>/.env` body naming the provider credential.

    Reasonix reads this file with a dotenv parser, so the value is JSON-quoted to
    survive whitespace and `#`.
    """
    return f"{KEY_ENV}={json.dumps(key)}\n"


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str], str]:
    """Return the Reasonix ACP command, child environment and config.toml text."""
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

    home = Path(home)
    child = {
        **environ,
        "HOME": str(home),
        # A set REASONIX_HOME makes the runtime fully self-contained: no legacy
        # migration and no OS-home scanning, so one Case cannot read another's
        # sessions, caches or credentials.
        "REASONIX_HOME": str(home),
        # ACP does not start the CLI telemetry reporter, and its policy is already
        # fail-closed; these keep it off if a later release moves the hook.
        "REASONIX_TELEMETRY": "off",
        "DO_NOT_TRACK": "1",
    }
    command = [
        REASONIX_BIN, "acp",
        # `--profile` is the ACP flag; the `--preset` spelling in upstream
        # docs/ACP.md belongs to `run`/`tui` and is rejected here.
        "--profile", "balanced",
        # Sessions otherwise open in `ask`; `auto` approves ordinary tool use
        # without prompting while keeping deny rules and plan confirmation.
        "--permission-mode", "auto",
        # Without this the Linux default is `enforce`, and bubblewrap cannot
        # create its namespaces inside a default container, so every shell
        # command is refused. The container is the boundary here.
        "--sandbox-bash", "auto",
        # Keep writes inside the Case workspace.
        "--workspace-only",
    ]
    return command, child, config_toml(base_url, model)


def main() -> int:
    home = None
    environ: dict[str, str] = {}
    try:
        # A disposable home keeps Reasonix's config, sessions and caches writable
        # by whichever unprivileged uid the runtime selects, and isolates Cases.
        home = Path(tempfile.mkdtemp(prefix="abb-reasonix-home-"))
        command, environ, config = prepare(dict(os.environ), home)
        (home / "config.toml").write_text(config, encoding="utf-8")
        credentials = home / ".env"
        credentials.write_text(credentials_env(environ[KEY_ENV]), encoding="utf-8")
        credentials.chmod(0o600)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1

    # ACP stdio is inherited directly: reasonix speaks spec ACP and needs no rewriting.
    child = subprocess.Popen(command, env=environ)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))
    return child.wait()


if __name__ == "__main__":
    raise SystemExit(main())
