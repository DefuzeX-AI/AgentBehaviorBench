import json

import pytest

from agentbench.harness.otel import create_session
from agentbench.harness.otel.config import parse_config
from agentbench.trajectory.agent_otel import operations
from agentbench.trajectory.atif.sources.langfuse import LangfuseSource, generation_usage


def test_official_callback_exports_generation_and_tool(tmp_path):
    pytest.importorskip("langfuse.langchain")
    from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
    from langchain_core.messages import AIMessage
    from langchain_core.tools import tool

    @tool
    def echo(value: str) -> str:
        """Return the value."""
        return value

    call = {"name": "echo", "args": {"value": "ping"}, "id": "call-1", "type": "tool_call"}
    model = FakeMessagesListChatModel(responses=[AIMessage(content="", tool_calls=[call])])
    session = create_session(parse_config({"framework": "langgraph"}), tmp_path, "test-graph")
    try:
        session.attach(None, "langgraph", "test-graph")
        assert session.handler is not None
        config = {"callbacks": [session.handler], "metadata": {"abb_invocation_id": "invoke-1"}}
        model.invoke("Call echo", config=config)
        echo.invoke(call, config=config)
    finally:
        session.close()

    rows = (tmp_path / "spans.jsonl").read_text(encoding="utf-8").splitlines()
    refs = ({"file": "otel/spans.jsonl", "line": n, "raw": json.loads(row)} for n, row in enumerate(rows, 1))
    source, issues = LangfuseSource(), []
    source.recorded(None, include_network=False, issues=issues)
    records = {record["kind"]: record for item in operations(refs) if (record := source.adopt(item, issues))}
    assert not issues
    assert records["model"]["output"]["tool_calls"] == [{"id": "call-1", "name": "echo", "arguments": {"value": "ping"}}]
    assert records["tool"]["tool_call_id"] == "call-1"
    assert records["tool"]["input_arguments"] == {"value": "ping"}
    assert records["tool"]["outputs"] == "ping"
    assert all(record["invocation_id"] == "invoke-1" for record in records.values())


def test_exclusive_langfuse_usage_and_overlapping_priority_tiers():
    usage = generation_usage({"input": 21, "input_cache_read": 9, "input_priority": 30,
                              "output": 2, "output_reasoning": 4, "total": 36})
    assert usage["prompt_tokens"] == 30 and usage["completion_tokens"] == 6
    assert usage["prompt_tokens_details"] == {"cached_tokens": 9}
