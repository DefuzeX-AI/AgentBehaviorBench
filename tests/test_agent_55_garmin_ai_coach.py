from __future__ import annotations

import asyncio
import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
BINDING = ROOT / "resources/agents/49-garmin-ai-coach/bindings/bridge.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("garmin_ai_coach_bridge", BINDING)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _request() -> dict[str, object]:
    return {
        "athlete_name": "Case Athlete",
        "current_date": "2026-10-09",
        "analysis_context": "Focus on recovery.",
        "planning_context": "Build conservatively.",
        "competitions": [{"name": "Example Race", "date": "2026-12-06"}],
        "garmin_data": {"metrics": {"training_load": 412}},
    }


def test_factory_is_zero_argument_and_normalises_dates() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()
    request = bridge._normalise_request(_request())

    assert session._closed is False
    assert request["user_id"] == "abb_case"
    assert request["current_date"] == {"date": "2026-10-09", "day_name": "Friday"}
    assert request["week_dates"][0] == "2026-10-09"
    assert request["week_dates"][-1] == "2026-10-22"
    assert request["hitl_enabled"] is False
    assert request["plotting_enabled"] is False


def test_text_input_extracts_json_and_rejects_unknown_fields() -> None:
    bridge = _load_bridge()
    embedded = f"Use this snapshot:\n```json\n{bridge.json.dumps(_request())}\n```"

    assert bridge._normalise_request(embedded)["athlete_name"] == "Case Athlete"
    with pytest.raises(ValueError, match="Unsupported top-level fields"):
        bridge._normalise_request({**_request(), "ignored": True})


def test_complete_native_result_is_exposed_without_new_model_calls() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()
    captured: dict[str, object] = {}

    async def fake_native(request, config):
        captured["request"] = request
        captured["config"] = config
        return {
            "metrics_outputs": {"load": "stable"},
            "synthesis_result": "Recovery is adequate.",
            "season_plan": {"phase": "base"},
            "weekly_plan": ["easy run", "rest"],
            "errors": [],
        }

    session._run_native = fake_native
    result = asyncio.run(session.ainvoke(_request(), config={"tags": ["abb"]}))

    assert captured["config"] == {"tags": ["abb"]}
    assert captured["request"]["skip_synthesis"] is False
    assert result["synthesis_result"] == "Recovery is adequate."
    assert "## Integrated analysis" in result["answer"]
    assert "## Season plan" in result["answer"]
    assert "## Weekly plan" in result["answer"]


def test_message_results_are_rendered_as_text() -> None:
    bridge = _load_bridge()

    class Message:
        content = "# Athlete Performance Report"
        additional_kwargs = {"refusal": None}

    result = bridge._public_result(
        {
            "synthesis_result": Message(),
            "season_plan": {"type": "ai", "content": [{"type": "text", "text": "Base phase."}]},
            "weekly_plan": {"phase": "base"},
        }
    )

    assert "## Integrated analysis\n\n# Athlete Performance Report" in result["answer"]
    assert "Base phase." in result["answer"]
    assert "additional_kwargs" not in result["answer"]
    assert '"phase": "base"' in result["answer"]


def test_plain_text_without_business_data_returns_needs_input() -> None:
    bridge = _load_bridge()
    result = asyncio.run(
        bridge.create_graph().ainvoke("Briefly introduce yourself: what can you help with?")
    )

    assert result["status"] == "needs_input"
    assert "athlete_name" in result["answer"]
    assert result["errors"][0]["type"] == "needs_input"


def test_closed_session_rejects_invocation() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()
    session.close()

    with pytest.raises(RuntimeError, match="closed"):
        session.invoke(_request())
