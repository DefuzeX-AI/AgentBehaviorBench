"""Drive OpenClaudia's native one-shot print frontend from ABB.

Upstream ``openclaudia acp`` speaks acpx Agent Control Protocol, not the Agent
Client Protocol ABB's ACP adapter expects. The supported non-interactive path
that preserves upstream provider/auth/print contracts is
``openclaudia --print`` (no tools, no session persistence).

OpenClaudia's reqwest client uses rustls-tls and ignores ``SSL_CERT_FILE``, so
this binding starts a loopback HTTP ``model_relay`` (same pattern as
113-sudocode) and points ``--target local`` at that relay. The relay forwards
to ``https://api.openai.com`` through the runtime ``HTTPS_PROXY`` using
Python's TLS stack, which honors the interceptor CA.

No filesystem or shell tools are available in print mode; the Agent Profile
must describe chat-only behaviour.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import model_relay

_WORKSPACE = Path(
    os.environ.get("ABB_CASE_WORKSPACE", "/home/agent/workspace")
)
# Binary must be on PATH. Do not use an OPENCLAUDIA_* name: config load rejects
# unknown OPENCLAUDIA_ environment variables.
_OPENCLAUDIA = os.environ.get("ABB_OPENCLAUDIA_BIN", "openclaudia")

_MINIMAL_CONFIG = """\
# ABB Case config for OpenClaudia print mode. The binding overrides
# providers.local.base_url to the loopback model relay at invoke time.
proxy:
  port: 8080
  host: "127.0.0.1"
  target: local

providers:
  local:
    base_url: http://127.0.0.1:9/v1
  openai:
    base_url: https://api.openai.com

session:
  timeout_minutes: 30
  persist_path: .openclaudia/session
"""


class OpenClaudiaBindingError(RuntimeError):
    """Raised when the native print frontend cannot complete."""


def _message_from_input(value: Any) -> str:
    """Accept nonempty text or exactly {'message': text}."""
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply text or exactly one message field")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("OpenClaudia print mode requires nonempty text")
    return value.strip()


def _require_openai_env() -> tuple[str, str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    if not key:
        raise OpenClaudiaBindingError(
            "OPENAI_API_KEY must be supplied by the interception worker"
        )
    model = (os.environ.get("OPENAI_MODEL") or "").strip()
    if not model:
        model = "gpt-4.1-mini"
    return key, model


def _failure_detail(stderr: str, stdout: str, returncode: int) -> str:
    """Prefer terminal Error lines over verbose tracing noise on stderr."""
    lines = [line.strip() for line in (stderr or "").splitlines() if line.strip()]
    interesting = [
        line
        for line in lines
        if line.startswith("Error:")
        or line.startswith("error:")
        or "ERROR" in line
        or "rejected" in line.lower()
        or "failed" in line.lower()
        or "unavailable" in line.lower()
    ]
    chosen = interesting[-8:] if interesting else lines[-12:]
    detail = "\n".join(chosen) if chosen else (stdout or f"exit {returncode}")
    return detail[:2000]


def _ensure_workspace() -> Path:
    _WORKSPACE.mkdir(parents=True, exist_ok=True)
    cfg_dir = _WORKSPACE / ".openclaudia"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg = cfg_dir / "config.yaml"
    cfg.write_text(_MINIMAL_CONFIG, encoding="utf-8")
    if not (_WORKSPACE / ".git").exists():
        subprocess.run(
            ["git", "init", "-q"],
            cwd=_WORKSPACE,
            check=False,
            capture_output=True,
        )
    return _WORKSPACE


class OpenClaudiaPrintBinding:
    """One Case: each invoke runs a fresh ``openclaudia --print`` process."""

    def __init__(self) -> None:
        self._closed = False
        self._tmpdir: tempfile.TemporaryDirectory[str] | None = None
        self._relay = None

    def invoke(self, value: Any, config: object | None = None, **kwargs: Any) -> dict[str, str]:
        del config, kwargs
        if self._closed:
            raise OpenClaudiaBindingError("This OpenClaudia Case has been closed")
        prompt = _message_from_input(value)
        api_key, model = _require_openai_env()
        workspace = _ensure_workspace()

        if self._relay is None:
            self._relay, relay_url = model_relay.start(
                model_relay.default_upstream(),
                bearer=api_key,
            )
        else:
            relay_url = f"http://127.0.0.1:{self._relay.server_address[1]}"

        env = os.environ.copy()
        env["OPENAI_API_KEY"] = api_key
        env.setdefault("HOME", str(Path.home()))
        env["OPENCLAUDIA_PROXY__TARGET"] = "local"
        # Local target skips SSRF reserved-IP checks; point at the HTTP relay.
        # OpenClaudia's openai-compatible adapter appends /v1/chat/completions.
        env["OPENCLAUDIA_PROVIDERS__LOCAL__BASE_URL"] = relay_url
        env["OPENCLAUDIA_BASH_SANDBOX"] = "off"
        env["RUST_LOG"] = "error"
        # Keep loopback off the interceptor HTTPS_PROXY path.
        no_proxy = ",".join(
            filter(
                None,
                [
                    env.get("NO_PROXY", ""),
                    env.get("no_proxy", ""),
                    "127.0.0.1",
                    "localhost",
                ],
            )
        )
        env["NO_PROXY"] = no_proxy
        env["no_proxy"] = no_proxy

        cmd = [
            _OPENCLAUDIA,
            "--target",
            "local",
            "--model",
            model,
            "--print",
            prompt,
        ]
        try:
            completed = subprocess.run(
                cmd,
                cwd=workspace,
                env=env,
                check=False,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("ABB_AGENT_INVOKE_TIMEOUT", "600")),
            )
        except FileNotFoundError as exc:
            raise OpenClaudiaBindingError(
                f"openclaudia binary not found ({_OPENCLAUDIA})"
            ) from exc
        except subprocess.TimeoutExpired as exc:
            raise OpenClaudiaBindingError("openclaudia --print timed out") from exc

        stdout = (completed.stdout or "").strip()
        stderr = (completed.stderr or "").strip()
        if completed.returncode != 0:
            detail = _failure_detail(stderr, stdout, completed.returncode)
            safe = detail.replace(api_key, "***")
            raise OpenClaudiaBindingError(f"openclaudia --print failed: {safe}")
        if not stdout:
            raise OpenClaudiaBindingError(
                "openclaudia --print returned empty stdout"
                + (f"; stderr={_failure_detail(stderr, '', 0)}" if stderr else "")
            )
        return {"message": stdout, "answer": stdout}

    async def ainvoke(
        self, value: Any, config: object | None = None, **kwargs: Any
    ) -> dict[str, str]:
        return self.invoke(value, config=config, **kwargs)

    def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        relay, self._relay = self._relay, None
        if relay is not None:
            try:
                relay.shutdown()
            except Exception:
                pass
        tmp, self._tmpdir = self._tmpdir, None
        if tmp is not None:
            tmp.cleanup()

    async def aclose(self) -> None:
        self.close()


def create_graph() -> OpenClaudiaPrintBinding:
    """Synchronous zero-argument factory required by ABB LangGraph adapter."""
    return OpenClaudiaPrintBinding()
