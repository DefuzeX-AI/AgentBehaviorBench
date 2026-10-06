from __future__ import annotations

from collections.abc import Generator
from pathlib import Path
import sys

import pytest
from fastapi.testclient import TestClient

# Ensure repository root is importable in CI (for `from main import create_app`).
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(autouse=True)
def disable_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_API_KEY", raising=False)
    monkeypatch.setenv("MCUBE_DISABLE_DOTENV", "1")
    # Force tests into deterministic stub mode.
    for key in (
        "LLM_PROVIDER",
        "LLM_MODEL",
        "LLM_VISION_MODEL",
        "LLM_BASE_URL",
        "OPENAI_API_KEY",
        "OPENAI_MODEL",
        "OPENAI_VISION_MODEL",
        "OPENAI_BASE_URL",
        "ANTHROPIC_API_KEY",
        "GEMINI_API_KEY",
        "MOONSHOT_API_KEY",
        "MINIMAX_API_KEY",
        "DASHSCOPE_API_KEY",
        "ARK_API_KEY",
        "DEEPSEEK_API_KEY",
        "ZHIPUAI_API_KEY",
    ):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def client() -> Generator[TestClient, None, None]:
    from main import create_app

    app = create_app()
    with TestClient(app) as test_client:
        yield test_client
