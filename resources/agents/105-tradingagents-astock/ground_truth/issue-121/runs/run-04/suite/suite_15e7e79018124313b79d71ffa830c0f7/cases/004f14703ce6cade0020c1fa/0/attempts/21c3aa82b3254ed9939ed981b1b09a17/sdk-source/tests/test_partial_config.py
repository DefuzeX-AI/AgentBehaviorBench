"""#101：README 快速开始只传 4 个键的 config 曾直接 KeyError('data_cache_dir')。"""
from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.graph.trading_graph import merge_config


def test_partial_config_is_merged_over_defaults():
    partial = {"llm_provider": "minimax", "deep_think_llm": "MiniMax-M2.7", "output_language": "Chinese"}
    merged = merge_config(partial)
    assert merged["llm_provider"] == "minimax"
    assert merged["deep_think_llm"] == "MiniMax-M2.7"
    assert merged["output_language"] == "Chinese"
    # README 示例没给的键必须从默认值补齐，__init__ 紧接着就要用它们建目录
    assert merged["data_cache_dir"] == DEFAULT_CONFIG["data_cache_dir"]
    assert merged["results_dir"] == DEFAULT_CONFIG["results_dir"]
    assert set(DEFAULT_CONFIG) <= set(merged)


def test_none_config_equals_defaults_but_is_a_copy():
    merged = merge_config(None)
    assert merged == DEFAULT_CONFIG
    assert merged is not DEFAULT_CONFIG
    merged["llm_provider"] = "changed-in-test"
    assert DEFAULT_CONFIG["llm_provider"] != "changed-in-test"


def test_user_nested_dict_replaces_default_wholesale():
    merged = merge_config({"role_llms": {"bull": {"provider": "openai", "model": "x"}}})
    assert merged["role_llms"] == {"bull": {"provider": "openai", "model": "x"}}
