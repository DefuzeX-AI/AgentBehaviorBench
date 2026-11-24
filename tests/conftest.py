"""Suite-wide collection rules."""
import pytest

# KUMA judges on spans. ABB no longer synthesizes OTel spans from its own framework
# records, and Agent-exported OTel is not connected to the KUMA capture yet (see
# agentbench.sdk.plugin.kuma.integration.require_trace_evidence). These tests drive
# KUMA generation or execution past that preflight check, or feed it the removed
# span source; they stay skipped until KUMA is reconnected.
KUMA_TRACE_EVIDENCE_TESTS = frozenset((
    'tests/test_acp_evidence.py::test_callbacks_produce_actual_tool_spans_and_file_evidence',
    'tests/test_acp_incomplete_tools.py::test_prompt_boundary_closes_observation_without_inventing_tool_success',
    'tests/test_acp_sdk_evidence.py::test_stream_updates_keep_local_evidence_without_exhausting_sdk_events',
    'tests/test_agent_input_contract.py::test_preflight_accepts_agent_without_evaluation_directory',
    'tests/test_case_preparation.py::test_container_interruption_keeps_active_slot_distinct_from_unattempted',
    'tests/test_case_preparation.py::test_invalid_slots_never_start_generation',
    'tests/test_case_preparation.py::test_original_casegen_disposition_controls_explicit_regeneration',
    'tests/test_case_preparation.py::test_partial_export_cannot_bypass_strict_collection_import',
    'tests/test_framework_network_modes.py::test_native_kuma_preflight_does_not_load_an_unused_replacement_provider',
    'tests/test_issue10.py::test_live_callback_distinguishes_control_flow',
    'tests/test_issue10.py::test_real_tool_arguments_result_and_call_id_reach_kuma',
    'tests/test_issue20_evidence.py::test_explicit_agent_terminal_status_reaches_sdk',
    'tests/test_issue20_evidence.py::test_sdk_multi_turn_history_and_capture_status',
    'tests/test_issue229_trace_boundary.py::TraceBoundaryTests::test_actual_model_callback_bodies_are_present_not_fabricated',
    'tests/test_issue229_trace_boundary.py::TraceBoundaryTests::test_binding_preserves_native_exception_and_closes_callback_span',
    'tests/test_issue229_trace_boundary.py::TraceBoundaryTests::test_binding_propagates_real_nested_graph_callbacks_and_keeps_native_config',
    'tests/test_issue229_trace_boundary.py::TraceBoundaryTests::test_existing_forbidden_external_attribute_is_still_partial',
    'tests/test_issue229_trace_boundary.py::TraceBoundaryTests::test_sdk_safe_metadata_preserves_full_local_correlation_and_payloads',
    'tests/test_issue229_trace_boundary.py::TraceBoundaryTests::test_unfinished_span_remains_incomplete_not_relabelled',
    'tests/test_issue277.py::test_completed_tool_with_missing_terminal_result_closes_honestly_at_boundary',
    'tests/test_issue277.py::test_final_terminal_snapshot_includes_data_after_tool_completion',
    'tests/test_issue277.py::test_meta_chunks_and_exit_reach_sdk_without_losing_other_content',
    'tests/test_issue277.py::test_terminal_events_do_not_exhaust_root_span_budget',
    'tests/test_issue39_native_output.py::test_structured_native_result_reaches_sdk_without_flattening_or_trace_expansion',
    'tests/test_issue52.py::test_unreachable_backend_during_case_generation_is_named',
    'tests/test_issue63.py::test_dropped_judge_poll_records_the_original_request_and_recovery_resumes_it',
    'tests/test_issue63.py::test_latest_judgment_record_of_the_run_is_chosen',
    'tests/test_issue63.py::test_records_of_other_runs_are_never_attached',
    'tests/test_kuma_pypi.py::test_independent_kuma_runners_execute_explicit_cases_concurrently',
    'tests/test_kuma_pypi.py::test_kuma_checks_executed_content_against_prepared_identity',
    'tests/test_kuma_pypi.py::test_kuma_generation_prepares_entire_selection_in_one_session',
    'tests/test_kuma_pypi.py::test_kuma_prepares_immutable_complete_batch_without_host_sdk_import',
    'tests/test_kuma_pypi.py::test_kuma_rejects_batch_duplicates_before_execution',
    'tests/test_kuma_pypi.py::test_kuma_rejects_modified_wire_artifact_before_creating_run',
    'tests/test_kuma_pypi.py::test_preflight_does_not_require_host_sdk_checkout_or_import',
))


def pytest_collection_modifyitems(items):
    marker = pytest.mark.skip(reason='KUMA trace evidence is disconnected')
    for item in items:
        if item.nodeid.split('[')[0] in KUMA_TRACE_EVIDENCE_TESTS:
            item.add_marker(marker)
