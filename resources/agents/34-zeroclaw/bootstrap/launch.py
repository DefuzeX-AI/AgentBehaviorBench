"""Map an OpenAI-compatible GLM profile onto ZeroClaw's native ACP server and relay its stdio."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import threading
from urllib.parse import urlsplit


KEY_ENV = "GLM_API_KEY"
BASE_URL_ENV = "GLM_API_BASE_URL"
MODEL_ENV = "GLM_MODEL"
ZEROCLAW = "/opt/zeroclaw/bin/zeroclaw"
# Provider slot `custom` (OpenAI chat-completions wire) with alias `abb`.
PROVIDER = "custom.abb"
AGENT = "abb"
# ZeroClaw's schema-mirror env override for providers.models.custom.abb.api_key:
# the key is resolved from the environment at startup and never written to disk.
KEY_OVERRIDE_ENV = "ZEROCLAW_providers__models__custom__abb__api_key"
# Permission option kinds defined by the ACP schema. ZeroClaw adds a non-standard
# `reject_with_edit` option to file_write/file_edit approvals (a Zed-style "edit
# the proposal" affordance) that a spec client cannot deserialize.
ACP_OPTION_KINDS = {"allow_once", "allow_always", "reject_once", "reject_always"}


def toml_str(value: str) -> str:
    return json.dumps(value)


def config_toml(base_url: str, model: str) -> str:
    """ZeroClaw config.toml (schema v3) for one Case; contains no credential."""
    return "\n".join([
        "schema_version = 3",
        "",
        "[providers.models.custom.abb]",
        f"uri = {toml_str(base_url)}",
        f"model = {toml_str(model)}",
        # Explicit chat-completions wire: the admitted route is /chat/completions.
        'wire_api = "chat_completions"',
        # GLM's chat-completions endpoint supports OpenAI function calling, but
        # ZeroClaw's `custom` slot defaults to its prompt-guided text fallback
        # (tool calls as <tool_call> text, no `tools` in the request). With
        # native tools the default "auto" dispatcher sends real tool schemas
        # and receives structured tool_calls.
        "native_tools = true",
        "",
        f"[agents.{AGENT}]",
        "enabled = true",
        f"model_provider = {toml_str(PROVIDER)}",
        'risk_profile = "abb"',
        'runtime_profile = "abb"',
        "",
        # Upstream's supervised posture: medium-risk tool calls (file writes,
        # shell) are sent to the ACP client as session/request_permission, the
        # workspace boundary is the ACP session cwd, and the built-in command
        # allowlist / forbidden paths stay at their defaults.
        "[risk_profiles.abb]",
        'level = "supervised"',
        "workspace_only = true",
        "",
        "[runtime_profiles.abb]",
        "agentic = true",
        "",
        # Network tools would be egress outside the admitted model route; they
        # are switched off instead of allowlisted so the model is not offered
        # tools that cannot work in this deployment.
        "[browser]",
        "enabled = false",
        "",
        "[http_request]",
        "enabled = false",
        "",
        "[web_fetch]",
        "enabled = false",
        "",
        "[web_search]",
        "enabled = false",
        "",
    ])


def prepare(environ: dict[str, str]) -> tuple[str, str, str]:
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
    return key, base_url, model


def adapt_agent_message(line: bytes) -> bytes:
    """Drop permission options whose kind is not in the ACP schema.

    ZeroClaw offers `reject_with_edit` next to the standard allow/reject options
    for file_write/file_edit approvals. The ACP Python SDK rejects the whole
    request_permission call on that unknown enum value, so the tool would be
    denied by a protocol error rather than by a permission decision. Removing
    only that extra option keeps every standard choice and ZeroClaw's own
    approval semantics unchanged.
    """
    if b'"session/request_permission"' not in line:
        return line
    try:
        message = json.loads(line)
    except ValueError:
        return line
    params = message.get("params") if isinstance(message, dict) else None
    if message.get("method") != "session/request_permission" or not isinstance(params, dict):
        return line
    options = params.get("options")
    if not isinstance(options, list):
        return line
    kept = [o for o in options if not isinstance(o, dict) or o.get("kind") in ACP_OPTION_KINDS]
    if len(kept) == len(options):
        return line
    params["options"] = kept
    return json.dumps(message, separators=(",", ":")).encode() + b"\n"


def relay(command: list[str], environ: dict[str, str]) -> int:
    """Run ZeroClaw as a child and relay ACP stdio, adapting permission requests."""
    child = subprocess.Popen(command, env=environ, stdin=subprocess.PIPE, stdout=subprocess.PIPE)
    for signum in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
        signal.signal(signum, lambda number, _frame: child.send_signal(number))

    def client_to_agent() -> None:
        try:
            for line in sys.stdin.buffer:
                child.stdin.write(line)
                child.stdin.flush()
        except (BrokenPipeError, OSError):
            pass
        finally:
            try:
                child.stdin.close()
            except OSError:
                pass

    threading.Thread(target=client_to_agent, daemon=True).start()
    out = sys.stdout.buffer
    try:
        for line in child.stdout:
            out.write(adapt_agent_message(line))
            out.flush()
    except (BrokenPipeError, OSError):
        child.terminate()
    return child.wait()


def main() -> int:
    try:
        key, base_url, model = prepare(dict(os.environ))
        # A disposable HOME keeps ZeroClaw's config, SQLite session store,
        # memory and runtime trace writable by whichever unprivileged uid the
        # runtime selects, and isolates Cases from each other.
        home = Path(tempfile.mkdtemp(prefix="abb-zeroclaw-home-"))
        config_dir = home / ".zeroclaw"
        config_dir.mkdir(mode=0o700)
        (config_dir / "config.toml").write_text(config_toml(base_url, model))
        environ = {k: v for k, v in os.environ.items() if k != KEY_ENV}
        environ.update({
            "HOME": str(home),
            "XDG_CONFIG_HOME": str(home / ".config"),
            "XDG_DATA_HOME": str(home / ".local/share"),
            "XDG_STATE_HOME": str(home / ".local/state"),
            "XDG_CACHE_HOME": str(home / ".cache"),
            KEY_OVERRIDE_ENV: key,
            "NO_COLOR": "1",
        })
        return relay([ZEROCLAW, "--config-dir", str(config_dir), "acp"], environ)
    except (OSError, ValueError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(message, file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
