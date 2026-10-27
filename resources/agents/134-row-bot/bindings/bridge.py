"""ABB LangGraph binding for siddsachar/row-bot (headless filesystem+calculator).

Registers one OpenAI-compatible custom endpoint from ABB interception env vars,
scopes the filesystem tool to the Case workspace, then invokes the native
``invoke_agent`` path. Desktop UI, FastAPI, and optional client builds stay out.
"""
from __future__ import annotations

import os
import sys
import tempfile
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

_UNIT_ROOT = Path(__file__).resolve().parents[1]
_SOURCE_ROOT = _UNIT_ROOT / "agent"
_WORKSPACE = Path(os.environ.get("ABB_CASE_WORKSPACE", "/home/agent/workspace"))
_TOOL_NAMES = ["filesystem", "calculator"]


def _prepare_env() -> Path:
    data = Path(os.environ.get("ROW_BOT_DATA_DIR") or tempfile.mkdtemp(prefix="abb-row-bot-"))
    data.mkdir(parents=True, exist_ok=True)
    os.environ["ROW_BOT_DATA_DIR"] = str(data)
    os.environ.setdefault("ROW_BOT_TEST_MODE", "1")
    os.environ.setdefault("ROW_BOT_AUTO_START_OLLAMA", "0")
    # Docker has no OS keyring. Seed the encrypted-file secret backend that
    # Row-Bot uses when keyring reports unavailable (including test mode).
    secrets_dir = data / "server-secrets"
    secrets_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    store_key = "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
    (secrets_dir / "ROW_BOT_SECRET_STORE_KEY").write_text(store_key, encoding="utf-8")
    os.environ["ROW_BOT_SECRETS_DIR"] = str(secrets_dir)
    _WORKSPACE.mkdir(parents=True, exist_ok=True)
    source = str(_SOURCE_ROOT.resolve())
    src_pkg = str((_SOURCE_ROOT / "src").resolve())
    for path in (source, src_pkg):
        if path not in sys.path:
            sys.path.insert(0, path)
    return data


def _require_model_env() -> tuple[str, str, str]:
    key = os.environ.get("OPENAI_API_KEY", "").strip()
    # Point at api.openai.com so ABB PEM interception can rewrite to the
    # runtime-selected provider; do not embed alternate provider secrets here.
    base = (
        os.environ.get("OPENAI_BASE_URL", "").strip().rstrip("/")
        or "https://api.openai.com/v1"
    )
    # Replacement-mode interception rewrites the request model; a stable local
    # label is enough when OPENAI_MODEL is unset (same pattern as other LangGraph units).
    model = (
        os.environ.get("OPENAI_MODEL", "").strip()
        or os.environ.get("DEEPSEEK_MODEL", "").strip()
        or "deepseek-chat"
    )
    if not key:
        raise RuntimeError("OPENAI_API_KEY must be supplied by ABB model interception")
    return key, base, model


def _configure_model(api_key: str, base_url: str, model_id: str) -> str:
    from row_bot.models import set_model
    from row_bot.providers.custom import save_custom_endpoint
    from row_bot.providers.selection import model_ref

    provider_id = "custom_openai_abb"
    snapshot = {
        "tasks": ["chat"],
        "input_modalities": ["text"],
        "output_modalities": ["text"],
        "transport": "openai_chat",
        "tool_calling": True,
    }
    save_custom_endpoint(
        {
            "id": "abb",
            "name": "ABB Interceptor",
            "base_url": base_url,
            "api_key": api_key,
            "auth_required": True,
            "enabled": True,
            "capability_probe": False,
            "profile": "generic_openai",
            "transport": "openai_chat",
            "execution_location": "remote",
            "models": [
                {
                    "id": model_id,
                    "model_id": model_id,
                    "label": model_id,
                    "ctx": 128000,
                    "context_window": 128000,
                    "provider": provider_id,
                    "capabilities_snapshot": snapshot,
                }
            ],
            "last_probe": {
                "model_id": model_id,
                "chat_ok": True,
                "tool_calling": True,
                "tool_round_trip": True,
            },
        }
    )
    selection = model_ref(provider_id, model_id)
    set_model(selection)
    return selection


def _configure_tools() -> None:
    import row_bot.tools  # noqa: F401 — registers built-ins
    from row_bot.tools import registry

    fs = registry.get_tool("filesystem")
    if fs is None:
        raise RuntimeError("filesystem tool failed to register")
    fs.set_config("workspace_root", str(_WORKSPACE))
    # Keep only the two tools this deployment exposes.
    for tool in list(registry.get_all_tools()):
        name = str(getattr(tool, "name", "") or "")
        if not name:
            continue
        try:
            registry.set_enabled(name, name in _TOOL_NAMES)
        except Exception:
            pass


def _extract_prompt(value: Any) -> str:
    if isinstance(value, Mapping):
        for key in ("message", "prompt", "input", "task", "query"):
            item = value.get(key)
            if isinstance(item, str) and item.strip():
                return item
        messages = value.get("messages")
        if isinstance(messages, list):
            for message in reversed(messages):
                if isinstance(message, Mapping) and message.get("role") == "user":
                    content = message.get("content")
                    if isinstance(content, str) and content.strip():
                        return content
                content = getattr(message, "content", None)
                if getattr(message, "type", "") == "human" and isinstance(content, str):
                    return content
    text = str(value or "").strip()
    return text or "Introduce yourself and list the tools available in this deployment."


def _format_result(result: Any) -> str:
    if isinstance(result, str):
        return result
    if isinstance(result, Mapping):
        if result.get("type") == "interrupt":
            return (
                "This Case paused for an interactive approval or question that is "
                "unavailable in headless ABB execution."
            )
        for key in ("output", "message", "content", "answer"):
            item = result.get(key)
            if isinstance(item, str) and item.strip():
                return item
        return str(result)
    return str(result)


class RowBotGraph:
    """Invokable wrapper around native ``invoke_agent``."""

    def __init__(self) -> None:
        _prepare_env()
        key, base, model = _require_model_env()
        _configure_tools()
        self._selection = _configure_model(key, base, model)
        self._enabled = list(_TOOL_NAMES)

    def invoke(self, value: Any, config: Any = None, **kwargs: Any) -> str:
        from row_bot.agent import invoke_agent

        prompt = _extract_prompt(value)
        run_config = {
            "configurable": {
                "thread_id": f"abb-{uuid.uuid4().hex[:12]}",
                "generation_id": uuid.uuid4().hex,
                "runtime_surface": "abb",
                "approval_mode": "approve",
            }
        }
        if isinstance(config, Mapping):
            nested = config.get("configurable")
            if isinstance(nested, Mapping):
                run_config["configurable"].update(dict(nested))
        result = invoke_agent(prompt, self._enabled, run_config)
        return _format_result(result)

    async def ainvoke(self, value: Any, config: Any = None, **kwargs: Any) -> str:
        import asyncio

        return await asyncio.to_thread(self.invoke, value, config, **kwargs)

    def close(self) -> None:
        return None

    async def aclose(self) -> None:
        self.close()


def create_graph() -> RowBotGraph:
    return RowBotGraph()
