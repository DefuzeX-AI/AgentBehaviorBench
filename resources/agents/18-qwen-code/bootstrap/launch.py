"""Prepare native Qwen settings, then replace this process with Qwen's ACP CLI.

Deployment only: no model calls, prompt rewriting, tool shims, or source edits.
stdout is reserved for the native JSON-RPC transport.
"""

import fnmatch
import json
import os
from pathlib import Path
import sys
import tempfile
from urllib.parse import urlsplit, urlunsplit

try:
    import tomllib
except ModuleNotFoundError:  # Host-side checks on ABB's supported Python 3.10.
    import tomli as tomllib


KEY_ENV = "QWEN_API_KEY"
DEFAULT_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1"


def checked_base_url(value, manifest):
    """Accept HTTPS Chat Completions endpoints already declared for this key.

    Never echo the supplied URL: malformed URLs can contain credentials. Route
    matching is a configuration preflight, not a substitute for the interceptor.
    """
    if any(char.isspace() or ord(char) < 32 for char in value):
        raise ValueError("QWEN_BASE_URL must not contain whitespace or control characters")
    try:
        url = urlsplit(value.rstrip("/"))
        valid = (url.scheme == "https" and url.hostname and url.username is None
                 and url.password is None and not url.query and not url.fragment
                 and not any(part in (".", "..") for part in url.path.split("/"))
                 and "%" not in url.path and "\\" not in value)
        port = 443 if url.port is None else url.port
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("QWEN_BASE_URL must be an HTTPS API base URL without credentials, query, or fragment")
    interception = manifest["llm_interception"]
    credentials = {item["id"] for item in interception["credentials"]
                   if item["agent_env"] == KEY_ENV and item["auth_plugin"] == "bearer-token"}
    path = url.path + "/chat/completions"
    for route in interception["routes"]:
        if (route.get("credential") in credentials
                and route["protocol_plugin"] == "openai-chat"
                and port in route["ports"] and "POST" in route["methods"]
                and any(fnmatch.fnmatchcase(url.hostname.lower(), host)
                        for host in route["host_patterns"])
                and any(fnmatch.fnmatchcase(path, pattern) for pattern in route["path_patterns"])):
            return urlunsplit((url.scheme, url.netloc, url.path, "", ""))
    raise ValueError("QWEN_BASE_URL is outside agent.toml's QWEN_API_KEY Chat Completions routes; declare its exact route first")


def prepare(unit, environ):
    """Return native argv/environment using an isolated, secret-free profile.

    The parent ACP adapter supplies only declared variables plus standard CA
    and proxy variables. Preserve those; never disable TLS verification.
    """
    key = environ.get(KEY_ENV, "").strip()
    model = environ.get("QWEN_MODEL", "").strip()
    if not key or any(char in key for char in ("\r", "\n", "\0")):
        raise ValueError("QWEN_API_KEY is required and must be a single-line API key")
    if not model or any(char.isspace() or ord(char) < 32 for char in model):
        raise ValueError("QWEN_MODEL is required and must be a model ID without whitespace")
    manifest = tomllib.loads((unit / "agent.toml").read_text(encoding="utf-8"))
    workspace = Path(manifest["adapter"]["cwd"])
    if not workspace.is_absolute() or Path.cwd().resolve() != workspace.resolve():
        raise ValueError("Launch Qwen through ABB in the declared container workspace")
    base_url = checked_base_url(environ.get("QWEN_BASE_URL", "").strip() or DEFAULT_BASE_URL, manifest)
    profile = Path(tempfile.mkdtemp(prefix="abb-qwen-", dir="/home/agent"))
    settings = {
        "modelProviders": {"openai": [{
            "id": model, "baseUrl": base_url, "envKey": KEY_ENV,
            "wireApi": "chat-completions",
        }]},
        "model": {"name": model, "baseUrl": base_url},
        "security": {"auth": {"selectedType": "openai"}, "folderTrust": {"enabled": True}},
        "general": {"enableAutoUpdate": False},
        "privacy": {"usageStatisticsEnabled": False},
        "telemetry": {"enabled": False},
    }
    # mkdtemp creates a private directory; files contain no API key.
    for name, data in (("settings.json", settings),
                       ("trustedFolders.json", {str(workspace): "TRUST_FOLDER"})):
        with (profile / name).open("x", encoding="utf-8") as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
    env = {
        **environ, KEY_ENV: key, "QWEN_HOME": str(profile),
        "QWEN_TELEMETRY_ENABLED": "false", "QWEN_USAGE_STATISTICS_ENABLED": "false",
        "QWEN_CODE_SKIP_UPDATE_CHECK_ONCE": "true", "QWEN_DISABLE_AUTO_TITLE": "1",
    }
    # No OAuth login, API key argv, -y/YOLO, session resumption, or custom prompt.
    return ["qwen", "--acp", "--auth-type", "openai", "--model", model,
            "--approval-mode", "default"], env


def main():
    """Keep ACP stdin/stdout intact and let ABB own process-group cleanup."""
    try:
        command, env = prepare(Path(__file__).resolve().parents[1], dict(os.environ))
        os.execvpe(command[0], command, env)
    except (OSError, ValueError, KeyError) as exc:
        message = str(exc).replace(os.environ.get(KEY_ENV) or "\0", "[REDACTED]")
        print(f"Qwen launch configuration failed: {message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
