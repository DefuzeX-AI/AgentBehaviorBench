from __future__ import annotations

import io

from agentbench.cli.terminal_ui.llm_activity import DOT_FRAMES, LLMActivity
from agentbench.runtime.interception import TraceEvent


def test_activity_dot_frames_keep_following_text_in_the_same_column() -> None:
    assert [len(frame) for frame in DOT_FRAMES] == [3, 3, 3]


def test_static_activity_prints_short_request_and_response() -> None:
    output: list[str] = []
    activity = LLMActivity(output.append, live_updates=False)

    activity.start_stage("Running Agent inputs and DefuzeX Judge...")
    activity.emit(
        TraceEvent(
            "llm_request",
            {
                "call_id": "call-1",
                "provider": "openrouter",
                "payload": {
                    "messages": [
                        {"role": "system", "content": "Be helpful."},
                        {
                            "role": "user",
                            "content": "abcdefghijklmnopqrstuvwxyz",
                        },
                    ]
                },
            },
        )
    )
    activity.emit(
        TraceEvent(
            "llm_response",
            {
                "call_id": "call-1",
                "status": 200,
                "latency_ms": 1250,
                "payload": {
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": "response body from the model",
                            }
                        }
                    ]
                },
            },
        )
    )
    activity.finish_stage("OK")

    assert "      Agent > abcdefghijklmnopqrstuvwxyz" in output
    assert "      Model < waiting..." in output
    assert "    LLM call 01 | openrouter | 200 | 00:01" in output
    assert "      Model < response body from the model" in output
    assert output[-1] == "  OK"


def test_activity_extracts_responses_input_and_tool_calls() -> None:
    output: list[str] = []
    activity = LLMActivity(output.append, live_updates=False)

    activity.emit(
        TraceEvent(
            "llm_request",
            {
                "call_id": "call-input",
                "payload": {
                    "input": [
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "old request"}
                            ],
                        },
                        {
                            "role": "user",
                            "content": [
                                {"type": "input_text", "text": "inspect repository"}
                            ],
                        }
                    ]
                },
            },
        )
    )
    activity.emit(
        TraceEvent(
            "llm_response",
            {
                "call_id": "call-input",
                "payload": {
                    "choices": [
                        {
                            "message": {
                                "tool_calls": [
                                    {"function": {"name": "search_code"}}
                                ]
                            }
                        }
                    ]
                },
            },
        )
    )

    assert "      Agent > inspect repository" in output
    assert output[-1] == "      Model < Tool: search_code"


def test_live_activity_tracks_concurrent_calls_and_clears_panel(
    monkeypatch,
) -> None:
    terminal = io.StringIO()
    monkeypatch.setattr("sys.stdout", terminal)
    activity = LLMActivity(
        live_updates=True,
        animation_interval=10,
    )

    activity.start_stage("Running Agent inputs and DefuzeX Judge...")
    activity.emit(
        TraceEvent(
            "llm_request",
            {"call_id": "call-1", "payload": {"prompt": "first request"}},
        )
    )
    activity.emit(
        TraceEvent(
            "llm_request",
            {"call_id": "call-2", "payload": {"prompt": "second request"}},
        )
    )
    activity.close()

    rendered = terminal.getvalue()
    assert "Agent > second request" in rendered
    assert "2 active" in rendered
    assert "\033[2K" in rendered


def test_activity_ignores_non_llm_events() -> None:
    output: list[str] = []
    activity = LLMActivity(output.append, live_updates=False)

    activity.emit(TraceEvent("interceptor_ready", {"agent_id": "example"}))
    activity.emit(TraceEvent("network_request", {"call_id": "call-1"}))

    assert output == []
