from scripts.benchmark_report.artifacts import redact, wilson
from scripts.benchmark_report.classification import primary_failure
from scripts.benchmark_report.render import render_report


def test_report_classifies_transport_audit_code_as_integration_failure():
    category, explanation = primary_failure(
        {
            "healthy": False,
            "acceptance_errors": [{"code": "ncbi_query_uri_too_long", "responses": 4}],
            "judge_status": "issue",
        },
        {"execution": "succeeded", "judge": "received"},
    )

    assert category == "integration_http_414"
    assert "414" in explanation


def test_report_redacts_nested_credentials_and_secret_values():
    source = {
        "Authorization": "Bearer visible-secret",
        "nested": {"api_key": "sk-or-v1-super-secret", "safe": "prefix sk-test-secret-value suffix"},
    }

    redacted = redact(source)

    assert redacted["Authorization"] == "[REDACTED]"
    assert redacted["nested"]["api_key"] == "[REDACTED]"
    assert "sk-test" not in redacted["nested"]["safe"]


def test_wilson_interval_contains_observed_rate():
    low, high = wilson(59, 71)

    assert low < 59 / 71 < high


def test_render_report_produces_filterable_standalone_html():
    data = {
        "meta": {
            "title": "test",
            "date": "2026-09-14",
            "generated_at": "now",
            "ledger": "docs/ledger.json",
            "campaign_status": "stopped",
            "campaign_stop_reason": "test",
        },
        "summary": {
            "runs": 1,
            "run_statuses": {"complete": 1},
            "attempts": 1,
            "healthy": 1,
            "failed": 0,
            "healthy_rate": 1.0,
            "unique_cases": 1,
            "reused_attempts": 0,
            "casegen_service_failures": 0,
            "casegen_skipped_slots": 0,
            "preparation_failures": 0,
            "judge_reports": 1,
            "judge_counts": {"pass": 1},
            "healthy_judge_counts": {"pass": 1},
            "judge_service_codes": {},
            "judge_issue_severities": {},
            "reports_with_evidence_gaps": 0,
            "failure_counts": {},
            "input_artifacts": 0,
            "input_statuses": {},
            "otel_statuses": {},
            "otel_spans": 0,
            "framework_spans": 0,
            "trace_reasons": {},
            "submitted_steps": 0,
            "trace_partial_steps": 0,
            "requests": {"judge_posts": 1},
            "first_seen": {"attempts": 1, "healthy": 1},
            "reused": {"attempts": 0, "healthy": 0},
        },
        "per_agent": [{"agent_id": "react-agent", "attempts": 1, "unique_cases": 1, "healthy": 1, "rate": 1.0, "wilson_low": 0.2, "wilson_high": 1.0, "judge": {"pass": 1}}],
        "by_turns": [{"turns": 0, "attempts": 1, "healthy": 1, "rate": 1.0}],
        "by_period": [{"period": "early", "attempts": 1, "healthy": 1, "rate": 1.0}],
        "duration_by_agent": [{"agent_id": "react-agent", "n": 0, "median_seconds": None, "mean_seconds": None, "p90_seconds": None, "max_seconds": None}],
        "runs": [{"index": 1, "suite_id": "suite", "agents": ["react-agent"], "selected_case_counts": {"react-agent": 1}, "planned": 1, "generated": 1, "attempted": 1, "healthy": 1, "status": "complete", "qualifying": False, "artifact": None}],
        "cases": [{"healthy": True, "judge_status": "pass", "agent_id": "react-agent", "failure_category": "none", "run_index": 1, "case_index": 0, "title": "A case", "inputs": [], "attempt_number": 1, "case_id": "case_1", "suite_id": "suite", "description": "description", "failure_label": "ok", "case": {}, "judge_report": {"status": "pass", "issues": [], "evidence_gaps": []}, "network": {}, "raw_files": {}, "secondary_failures": [], "review_flags": [], "scope_review": None}],
        "casegen_failures": [],
        "casegen_skips": [],
        "preparation_failures": [],
        "native_observations": [],
        "usage": {},
        "live_3x5": {},
        "source_documents": [],
    }

    page = render_report(data)

    assert page.startswith("<!doctype html>")
    assert 'id="case-list"' in page
    assert "A case" in page
