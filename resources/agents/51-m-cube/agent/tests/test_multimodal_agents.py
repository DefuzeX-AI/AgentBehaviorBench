from __future__ import annotations

from agents.base_agent import BaseStructuredAgent, RetryPolicy
from agents.drafter_agents import drawing_analyze_node
from agents.oa_agents import analyze_prior_art_visual_node
from models.image_schemas import DrawingMap, PriorArtVisualReport


def test_drawing_analyze_node_without_images_returns_warning_map() -> None:
    def llm_stub(_: str, __: dict[str, object]):
        return {"figures": [], "overall_notes": "ok", "warnings": []}

    agent = BaseStructuredAgent[DrawingMap](
        name="drawing_test",
        llm_callable=llm_stub,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )
    output = drawing_analyze_node(
        {
            "session_id": "s1",
            "trace_id": "t1",
            "status": "running",
            "disclosure_text": "sample disclosure",
            "disclosure_images": [],
            "vision_warnings": [],
        },
        agent,
    )
    assert output["current_step"] == "drawing_analyze_node"
    assert isinstance(output["drawing_map"], dict)
    assert len(output["vision_warnings"]) >= 1


def test_analyze_prior_art_visual_node_with_missing_images_adds_warning() -> None:
    def llm_stub(_: str, __: dict[str, object]):
        return {"cited_figure_refs": [], "diffs": [], "conclusion": "ok"}

    agent = BaseStructuredAgent[PriorArtVisualReport](
        name="oa_visual_test",
        llm_callable=llm_stub,
        retry_policy=RetryPolicy(max_retries=1, initial_backoff_seconds=0, backoff_multiplier=1),
    )
    output = analyze_prior_art_visual_node(
        {
            "session_id": "s1",
            "trace_id": "t1",
            "status": "running",
            "oa_text": "examiner cites D1 Fig.2",
            "application_images": [],
            "prior_art_images": [],
            "vision_warnings": [],
        },
        agent,
    )
    assert isinstance(output["visual_report"], dict)
    assert len(output["vision_warnings"]) >= 1
