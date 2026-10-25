"""Map the selected OpenAI-compatible model profile onto Codewhale's native ACP server.

Codewhale refuses ambient credentials on a custom endpoint: a provider route must
bind its key explicitly (`docs/CONFIGURATION.md`, "runtime thread route"). The
launcher therefore writes a per-Case `config.toml` that names an environment
variable rather than a secret, and passes the actual key only in the child
environment. Nothing containing the key is written to disk or argv.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import sys
import tempfile
from urllib.parse import urlsplit

KEY_ENV = "ABB_AGENT_MODEL_API_KEY"
BASE_URL_ENV = "ABB_AGENT_MODEL_BASE_URL"
MODEL_ENV = "ABB_AGENT_MODEL"
# The config refers to this variable; the value is only ever exported to the child.
KEY_VARIABLE = "ABB_CODEWHALE_MODEL_KEY"
AGENT_DIR = Path(__file__).resolve().parents[1] / "agent"
# The npm package's own installer places the single native binary here.
DOWNLOADED_BINARY = AGENT_DIR / "node_modules/codewhale/bin/downloads"


def toml_string(value: str) -> str:
    """JSON string escaping is valid TOML basic-string syntax for these values."""
    return json.dumps(value)


def codewhale_binary() -> str:
    """Exec the native binary directly, falling back to the npm loader."""
    for candidate in (DOWNLOADED_BINARY / "codewhale", AGENT_DIR / "node_modules/.bin/codewhale"):
        if candidate.is_file() and os.access(candidate, os.X_OK):
            # The native binary avoids keeping an extra Node.js loader resident
            # under the container's memory limit.
            return str(candidate)
    raise ValueError(
        f"codewhale binary not found under {DOWNLOADED_BINARY} or node_modules/.bin; "
        "the image build must run the package installer"
    )


def chat_path_suffix(base_url: str) -> str:
    """Codewhale strips a trailing version segment (vN or beta) from base_url before
    appending path_suffix (upstream_url/unversioned_base_url in
    crates/app-server/src/chat_completions.rs), so keep that segment in the suffix;
    otherwise `https://api.b.ai/v1` becomes `https://api.b.ai/chat/completions`
    and misses the admitted `<base_url>/chat/completions` route."""
    last = urlsplit(base_url).path.rstrip("/").rsplit("/", 1)[-1]
    version = last.lower() == "beta" or (last[:1] in "vV" and last[1:].isdigit() and len(last) > 1)
    return f"/{last}/chat/completions" if version else "/chat/completions"


def render_config(base_url: str, model: str) -> str:
    """Return the config.toml that binds the shared model route explicitly."""
    return "\n".join([
        f'provider = "openai"',
        f"default_text_model = {toml_string(model)}",
        # A headless ACP session otherwise exposes file tools only: the model saw no
        # shell tool at all ("no shell or command-execution tool in its catalog").
        # ABB's ACP permission policy grants the request, so the Agent may run the
        # commands a coding task needs; the container remains the sandbox.
        "allow_shell = true",
        "",
        "[providers.openai]",
        f"base_url = {toml_string(base_url)}",
        # The runtime admits exactly `<base_url>/chat/completions`; Codewhale's
        # OpenAI route would otherwise append its own `/v1/chat/completions` and
        # miss that route, so the suffix is pinned to the admitted path.
        f"path_suffix = {toml_string(chat_path_suffix(base_url))}",
        # The key itself is never written here; Codewhale reads this variable from
        # the environment, which the runtime fills for this process only.
        f"api_key_env = {toml_string(KEY_VARIABLE)}",
        "",
    ])


def prepare(environ: dict[str, str], home: Path) -> tuple[list[str], dict[str, str]]:
    """Return the Codewhale ACP command and environment without persisting secrets."""
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

    codewhale_home = home / ".codewhale"
    codewhale_home.mkdir(parents=True, exist_ok=True)
    config_path = home / "config.toml"
    config_path.write_text(render_config(base_url, model), encoding="utf-8")
    config_path.chmod(0o600)
    # Diagnostics without secrets: the resolved route host/path and the proxy
    # variables the Agent will inherit decide whether model traffic is interceptable.
    print(
        f"abb-codewhale: base_url={base_url} model={model} "
        f"HTTPS_PROXY={environ.get('HTTPS_PROXY', '-')} "
        f"HTTP_PROXY={environ.get('HTTP_PROXY', '-')} "
        f"NO_PROXY={environ.get('NO_PROXY', '-')}",
        file=sys.stderr, flush=True,
    )

    child = dict(environ)
    child.update({
        KEY_VARIABLE: key,
        "CODEWHALE_CONFIG_PATH": str(config_path),
        "CODEWHALE_HOME": str(codewhale_home),
        # Telemetry and the self-updater would leave the admitted route; both are
        # switched off here rather than in a committed config file.
        "CODEWHALE_TELEMETRY": "0",
        "CODEWHALE_NO_UPDATE_CHECK": "1",
        "NO_COLOR": "1",
    })
    # OpenTelemetry export is only enabled when these are set; keep it off.
    for name in ("OTEL_EXPORTER_OTLP_ENDPOINT", "OTEL_EXPORTER_OTLP_PROTOCOL",
                 "OTEL_SDK_DISABLED"):
        child.pop(name, None)
    return [codewhale_binary(), "serve", "--acp"], child


def main() -> int:
    home = Path(tempfile.mkdtemp(prefix="abb-codewhale-home-"))
    try:
        # A disposable HOME keeps Codewhale's sessions and logs writable by whichever
        # unprivileged uid the runtime selects, and isolated per Case.
        child_home = {
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_CACHE_HOME": str(home / ".cache"),
        }
        for value in child_home.values():
            Path(value).mkdir(parents=True, exist_ok=True)
        environ = {**os.environ, **child_home}
        command, child = prepare(environ, home)
        os.execvpe(command[0], command, child)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
