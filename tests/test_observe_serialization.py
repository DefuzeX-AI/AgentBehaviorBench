"""Preserve actual nested message fields at the framework log boundary."""
import json

import pytest

from agentbench.observe.store import TraceStore, json_value


def test_nested_ai_message_survives_callback_log_with_redaction(tmp_path):
    from langchain_core.messages import AIMessage
    from langchain_core.outputs import ChatGeneration, LLMResult
    from agentbench.observe.langchain import TraceCallback

    secret = "fixture-serialization-secret-12345"
    usage = {"input_tokens": 2, "output_tokens": 3, "total_tokens": 5}
    message = AIMessage(
        content="你好，¡Hola! " + secret,
        tool_calls=[{"name": "calculate_sum", "args": {"a": 19, "b": 23}, "id": "call-test"}],
        usage_metadata=usage,
        response_metadata={"api_key": secret, "model_name": "fixture"},
    )
    result = LLMResult(generations=[[ChatGeneration(message=message)]])
    log = tmp_path / "framework.jsonl"
    callback = TraceCallback(TraceStore(log, "run", source="framework",
                                       environ={"OPENROUTER_API_KEY": secret}))
    callback.on_llm_end(result, run_id="model")
    text = log.read_text(encoding="utf-8")
    row = json.loads(text)
    saved = row["data"]["output"]["generations"][0][0]["message"]
    assert row["event"] == "span_end" and row["data"]["span_id"] == "model"
    assert saved["usage_metadata"] == usage
    assert saved["tool_calls"] == message.tool_calls
    assert saved["content"] == "你好，¡Hola! [REDACTED]"
    assert saved["response_metadata"] == {"api_key": "[REDACTED]", "model_name": "fixture"}
    assert secret not in text
    assert message.content.endswith(secret)  # Logging must not mutate the original message.


def test_model_dump_without_duck_typing_option_remains_supported():
    class LegacyValue:
        def model_dump(self):
            return {"nested": {"value": 42}}

    assert json_value(LegacyValue()) == {"nested": {"value": 42}}


def test_model_dump_failure_is_not_silently_retried():
    class BrokenValue:
        def model_dump(self, *, serialize_as_any=False):
            raise TypeError("serialization failed")

    with pytest.raises(TypeError, match="serialization failed"):
        json_value(BrokenValue())
