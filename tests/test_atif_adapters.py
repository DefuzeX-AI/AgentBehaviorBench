from tests.atif_fixtures import child_bundle
from agentbench.trajectory.atif.adapters.deepagents import DeepAgentsAdapter
from agentbench.trajectory.atif.adapters.opencode import OpenCodeAdapter


def test_task_name_alone_does_not_mean_delegation(tmp_path):
    bundle = child_bundle(tmp_path)
    for span in bundle.spans.values():
        span["metadata"] = {}
        if span["kind"] == "tool":
            span["name"] = "task"
    assert not DeepAgentsAdapter().identify(bundle).nodes


def test_acp_prose_does_not_create_children(tmp_path):
    bundle = child_bundle(tmp_path)
    bundle.native_events = [{"data": {"update": {"content": "I started two subagents sessionId=ses-123"}}}]
    result = OpenCodeAdapter().identify(bundle)
    assert not result.nodes
    assert result.issues[0].code == "native_hierarchy_not_observed"


def test_acp_structured_relation_without_internals_is_explicit_gap(tmp_path):
    bundle = child_bundle(tmp_path)
    bundle.native_events = [{"data": {"update": {"toolCallId": "delegate", "_meta": {
        "parentSessionId": "parent", "sessionId": "child"}}}}]
    result = OpenCodeAdapter().identify(bundle)
    assert not result.nodes
    assert result.issues[0].code == "native_child_records_missing"


def test_acp_native_response_and_turn_identity_can_form_child(tmp_path):
    bundle = child_bundle(tmp_path)
    tool = next(t for t in bundle.tools if t["tool_call_id"] == "delegate-call-one")
    model = bundle.models[0]
    model["raw_response"]["payload"]["id"] = "provider-response"
    bundle.native_events = [
        {"data": {"update": {"toolCallId": tool["tool_call_id"], "rawOutput": {"metadata": {
            "parentSessionId": "parent", "sessionId": "child"}}}}},
        {"data": {"native_session_id": "child", "native_turn_id": "turn-1", "native_response_id": "provider-response"}}]
    result = OpenCodeAdapter().identify(bundle)
    assert len(result.nodes) == 1
    assert result.nodes[0].record_ids == [model["id"]]
    assert result.facts[0]["status"] == "native_models_linked"
    # The same session is not enough to split multiple native turns.
    bundle.native_events.append({"data": {"native_session_id": "child", "native_turn_id": "turn-2", "native_response_id": "other-response"}})
    assert not OpenCodeAdapter().identify(bundle).nodes
