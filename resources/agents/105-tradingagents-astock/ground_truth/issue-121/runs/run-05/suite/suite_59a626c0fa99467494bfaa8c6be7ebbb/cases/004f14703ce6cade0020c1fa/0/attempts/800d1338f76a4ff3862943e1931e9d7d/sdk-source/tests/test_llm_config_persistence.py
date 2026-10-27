"""Web 侧栏 LLM 配置持久化（#96）的回归：位置、恢复、写失败不打断。"""

from __future__ import annotations

import json
import types

import pytest

from web.components import sidebar


@pytest.fixture()
def fake_st(monkeypatch, tmp_path):
    st = types.SimpleNamespace(session_state={})
    monkeypatch.setattr(sidebar, "st", st)
    monkeypatch.setattr(sidebar, "_LLM_CONFIG_PATH", tmp_path / "home" / ".tradingagents" / "llm_config.json")
    return st


@pytest.mark.unit
def test_config_file_lives_under_user_home():
    # 不能在包目录里：pip 安装时那是 site-packages，git 用户则会多出未跟踪文件
    assert sidebar._LLM_CONFIG_PATH.parent.name == ".tradingagents"
    assert "tradingagents" not in sidebar._LLM_CONFIG_PATH.parent.parent.name


@pytest.mark.unit
def test_save_creates_parent_dir_and_roundtrips_scope(fake_st):
    fake_st.session_state.update({
        "llm_provider": "deepseek", "quick_model_idx": 2, "deep_model_idx": 1,
        "llm_base_url": "https://relay.example/v1", "subscription_scope": "deep",
        "agent_sdk_model": "opus", "custom_quick_model": "my-q",
    })
    sidebar._save_llm_config()
    saved = json.loads(sidebar._LLM_CONFIG_PATH.read_text())
    assert saved["llm_provider"] == "deepseek" and saved["subscription_scope"] == "deep"

    fake_st.session_state.clear()
    sidebar._load_saved_llm_config()
    ss = fake_st.session_state
    assert ss["llm_provider_idx"] == sidebar._PROVIDER_KEYS.index("deepseek")
    assert ss["quick_model_idx"] == 2 and ss["deep_model_idx"] == 1
    assert ss["llm_base_url"] == "https://relay.example/v1"
    # selectbox 的 widget 键是 subscription_scope_idx —— 只回填派生值等于没恢复
    assert ss["subscription_scope_idx"] == sidebar._SCOPE_VALUES.index("deep")
    assert ss["agent_sdk_model"] == "opus" and ss["custom_quick_model"] == "my-q"


@pytest.mark.unit
def test_load_does_not_override_in_session_choice(fake_st):
    sidebar._LLM_CONFIG_PATH.parent.mkdir(parents=True)
    sidebar._LLM_CONFIG_PATH.write_text(json.dumps({"llm_provider": "openai", "subscription_scope": "all"}))
    fake_st.session_state["llm_provider_idx"] = 0
    fake_st.session_state["subscription_scope_idx"] = 0
    sidebar._load_saved_llm_config()
    assert fake_st.session_state["llm_provider_idx"] == 0
    assert fake_st.session_state["subscription_scope_idx"] == 0


@pytest.mark.unit
def test_unknown_scope_or_provider_falls_back_to_first(fake_st):
    sidebar._LLM_CONFIG_PATH.parent.mkdir(parents=True)
    sidebar._LLM_CONFIG_PATH.write_text(json.dumps({"llm_provider": "gone", "subscription_scope": "weird"}))
    sidebar._load_saved_llm_config()
    assert fake_st.session_state["llm_provider_idx"] == 0
    assert fake_st.session_state["subscription_scope_idx"] == 0


@pytest.mark.unit
def test_write_failure_only_warns(fake_st, monkeypatch, caplog):
    # 父目录位置被一个普通文件占住 → mkdir 抛 OSError；持久化失败不得冒泡
    blocker = sidebar._LLM_CONFIG_PATH.parent.parent
    blocker.parent.mkdir(parents=True, exist_ok=True)
    blocker.write_text("not a dir")
    sidebar._save_llm_config()  # must not raise
    assert any("持久化失败" in r.getMessage() for r in caplog.records)
