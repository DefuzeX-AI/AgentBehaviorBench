from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / "resources/agents/58-zeroapp"
BINDING = UNIT / "bindings/bridge.py"


def _load_bridge():
    spec = importlib.util.spec_from_file_location("zeroapp_bridge", BINDING)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(apps=None, accepted=1, rejected=0, average=82.5, requested=1, attempts=1):
    return {
        "requested": requested,
        "attempts": attempts,
        "accepted": accepted,
        "rejected": rejected,
        "average_score": average,
        "apps": apps
        if apps is not None
        else [
            {
                "app_name": "Pomodoro Focus",
                "slug": "pomodoro-focus",
                "verdict": "accept",
                "scored": "accept",
                "score": 82.5,
                "hap": "",
                "metrics": {
                    "views": 6,
                    "features": 9,
                    "charts": 3,
                    "collections": 4,
                    "records": 120,
                    "asset_bytes": 48000,
                    "files": 7,
                    "runtime_ok": None,
                    "runtime_note": "node is not on PATH",
                },
                "error": "",
            }
        ],
    }


def test_factory_is_zero_argument_and_session_starts_open() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()

    assert isinstance(session, bridge.ZeroAppBinding)
    assert session._closed is False
    assert session._workspace is None


def test_text_brief_uses_first_line_as_name_and_bullets_as_features() -> None:
    bridge = _load_bridge()
    text = (
        "Pomodoro Focus\n"
        "A focus timer for students who procrastinate.\n"
        "- 25 minute work timer\n"
        "- task list\n"
        "- daily streak\n"
    )

    briefs = bridge._parse_case_input(text)

    assert len(briefs) == 1
    assert briefs[0]["app_name"] == "Pomodoro Focus"
    assert "procrastinate" in briefs[0]["description"]
    assert briefs[0]["features"] == ["25 minute work timer", "task list", "daily streak"]


def test_markdown_heading_first_line_is_treated_as_the_name() -> None:
    bridge = _load_bridge()

    briefs = bridge._parse_case_input("# Habit Tracker\nLog daily habits.")

    assert briefs[0]["app_name"] == "Habit Tracker"
    assert briefs[0]["description"] == "Log daily habits."


def test_list_marker_on_the_name_line_is_stripped() -> None:
    bridge = _load_bridge()

    assert bridge._parse_case_input("1. Budget Planner\nTrack spending.")[0]["app_name"] == "Budget Planner"
    assert bridge._parse_case_input("- Budget Planner\nTrack spending.")[0]["app_name"] == "Budget Planner"


def test_a_name_starting_with_a_digit_keeps_its_digits() -> None:
    """A leading-digit product name must not be clipped by marker stripping."""

    bridge = _load_bridge()

    briefs = bridge._parse_case_input("3D Printer Tracker\nLog every print job.")

    assert briefs[0]["app_name"] == "3D Printer Tracker"


def test_single_line_brief_keeps_the_full_description() -> None:
    """A long one-line brief must not lose text to the 80-char name clip."""

    bridge = _load_bridge()
    text = "Inventory sync tool for small warehouses that need stock counts, reorder alerts, and supplier lead times"

    briefs = bridge._parse_case_input(text)

    assert briefs[0]["app_name"] == text[:80].rstrip()
    assert briefs[0]["description"] == text
    assert len(briefs[0]["description"]) > 80


def test_an_overlong_name_is_clipped_but_the_brief_stays_buildable() -> None:
    bridge = _load_bridge()

    briefs = bridge._parse_case_input("A" * 200 + "\nShort description.")

    assert len(briefs[0]["app_name"]) == 80
    assert briefs[0]["description"] == "Short description."


def test_json_object_maps_native_brief_fields() -> None:
    bridge = _load_bridge()
    payload = {
        "app_name": "Pomodoro Focus",
        "description": "A focus timer.",
        "features": ["timer", "task list"],
        "pages": ["home", "stats"],
        "target_users": "students",
        "theme_color": "#3F6AE8",
        "slug": "pomodoro",
        "version_name": "1.2.0",
        "version_code": 1002000,
    }

    briefs = bridge._parse_case_input(json.dumps(payload))

    assert briefs[0] == {
        "app_name": "Pomodoro Focus",
        "description": "A focus timer.",
        "features": ["timer", "task list"],
        "pages": ["home", "stats"],
        "target_users": "students",
        "theme_color": "#3F6AE8",
        "slug": "pomodoro",
        "version_name": "1.2.0",
        "version_code": 1002000,
    }


def test_title_and_comma_separated_features_are_normalised() -> None:
    bridge = _load_bridge()

    briefs = bridge._parse_case_input({"title": "Habit Log", "core_features": "streak, reminders"})

    assert briefs[0]["app_name"] == "Habit Log"
    assert briefs[0]["features"] == ["streak", "reminders"]


def test_empty_optional_fields_fall_back_to_upstream_defaults() -> None:
    bridge = _load_bridge()

    briefs = bridge._parse_case_input({"app_name": "Habit Log", "slug": "", "pages": [], "design_notes": ""})

    assert briefs[0] == {"app_name": "Habit Log"}


def test_batch_input_exercises_the_native_fan_out() -> None:
    bridge = _load_bridge()

    briefs = bridge._parse_case_input(
        {"apps": [{"app_name": "First"}, {"title": "Second"}, "Third app\nA plain text brief."]}
    )

    assert [brief["app_name"] for brief in briefs] == ["First", "Second", "Third app"]


def test_json_embedded_in_prose_is_extracted() -> None:
    bridge = _load_bridge()

    briefs = bridge._parse_case_input('Build this please: {"app_name": "Pomodoro Focus"} thanks')

    assert briefs[0]["app_name"] == "Pomodoro Focus"


def test_text_brief_always_yields_a_name_from_its_first_line() -> None:
    """Documented intake contract: for a text brief the first line is the name.

    Upstream's own CLI takes the app name this way, so arbitrary prose still
    produces a buildable brief rather than being silently dropped.
    """

    bridge = _load_bridge()

    briefs = bridge._parse_case_input("help me with something")

    assert briefs == [
        {
            "app_name": "help me with something",
            "description": "help me with something",
        }
    ]


@pytest.mark.parametrize(
    "value",
    [
        "",
        "   \n  ",
        {},
        {"description": "no name at all"},
        {"features": ["timer"]},
        [{"title": ""}],
        {"apps": [{"description": "still no name"}]},
    ],
)
def test_structured_input_without_a_name_needs_input(value) -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()

    result = asyncio.run(session.ainvoke(value))

    assert result["status"] == "needs_input"
    assert result["errors"][0]["type"] == "needs_input"
    assert "app_name" in result["answer"]
    # The native factory must not have been reached at all.
    assert session._workspace is None


@pytest.mark.parametrize("value", [42, [42], 3.5, True])
def test_non_text_non_mapping_input_raises(value) -> None:
    bridge = _load_bridge()

    with pytest.raises(ValueError):
        bridge._parse_case_input(value)


def test_bad_version_code_is_rejected_rather_than_coerced() -> None:
    bridge = _load_bridge()

    with pytest.raises(ValueError, match="version_code"):
        bridge._parse_case_input({"app_name": "Pomodoro", "version_code": "soon"})


def test_native_report_is_projected_without_claiming_a_package_or_store() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()
    captured: dict[str, object] = {}

    async def fake_native(briefs, config):
        captured["briefs"] = briefs
        captured["config"] = config
        return _report()

    session._run_native = fake_native
    result = asyncio.run(
        session.ainvoke(
            {"app_name": "Pomodoro Focus", "description": "A focus timer."},
            config={"configurable": {"thread_id": "case-1"}},
        )
    )

    assert captured["config"] == {"configurable": {"thread_id": "case-1"}}
    assert captured["briefs"][0]["app_name"] == "Pomodoro Focus"
    assert result["status"] == "finished"
    assert result["accepted"] == 1
    assert result["errors"] == []

    answer = result["answer"]
    assert "Pomodoro Focus" in answer
    assert "verdict: accept" in answer
    assert "runtime=skipped" in answer
    # The deployment builds nothing and publishes nowhere; the answer must say so
    # instead of implying an artifact or a store submission exists.
    assert "not built (build disabled in this deployment)" in answer
    assert "nothing was uploaded to any app store" in answer
    assert ".hap" not in answer.split("no .hap artifact exists")[0]


def test_rejected_verdict_is_preserved_not_rewritten_as_success() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()

    async def fake_native(briefs, config):
        return _report(
            apps=[
                {
                    "app_name": "Thin App",
                    "slug": "thin-app",
                    "verdict": "reject",
                    "score": 12.0,
                    "hap": "",
                    "metrics": {"views": 1, "features": 1, "runtime_ok": False},
                    "error": "web asset generation failed: LLM failed on plan",
                }
            ],
            accepted=0,
            rejected=1,
            average=12.0,
        )

    session._run_native = fake_native
    result = asyncio.run(session.ainvoke({"app_name": "Thin App"}))

    assert result["accepted"] == 0
    assert result["rejected"] == 1
    assert "verdict: reject" in result["answer"]
    assert "runtime=failed" in result["answer"]
    assert "web asset generation failed" in result["answer"]
    assert "verdict: accept" not in result["answer"]


def test_native_failure_propagates_instead_of_being_reported_as_a_pass() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()

    async def fake_native(briefs, config):
        raise RuntimeError("LLM failed on plan")

    session._run_native = fake_native

    with pytest.raises(RuntimeError, match="LLM failed on plan"):
        asyncio.run(session.ainvoke({"app_name": "Pomodoro Focus"}))


def test_non_mapping_native_result_is_rejected() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()

    async def fake_native(briefs, config):
        return "not a report"

    session._run_native = fake_native

    with pytest.raises(bridge.ZeroAppBindingError, match="expected a report mapping"):
        asyncio.run(session.ainvoke({"app_name": "Pomodoro Focus"}))


def test_sync_invoke_delegates_to_the_async_path() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()

    async def fake_native(briefs, config):
        return _report()

    session._run_native = fake_native
    result = session.invoke({"app_name": "Pomodoro Focus"})

    assert result["status"] == "finished"


def test_close_removes_the_temporary_workspace_and_blocks_reuse() -> None:
    bridge = _load_bridge()
    session = bridge.create_graph()
    original = bridge.ZeroAppBinding._run_native

    async def recording_native(self, briefs, config):
        # Let the real implementation create the workspace, then short-circuit
        # before any upstream import so the test stays offline.
        import tempfile

        self._workspace = tempfile.mkdtemp(prefix="abb-zeroapp-test-")
        return _report()

    # Patch on the class, not the instance: an instance attribute would shadow
    # the patch and the workspace would never be created.
    bridge.ZeroAppBinding._run_native = recording_native
    try:
        asyncio.run(session.ainvoke({"app_name": "Pomodoro Focus"}))
    finally:
        bridge.ZeroAppBinding._run_native = original

    assert session._workspace is not None
    workspace = Path(session._workspace)
    assert workspace.is_dir()

    session.close()

    assert session._closed is True
    assert session._workspace is None
    assert not workspace.exists()
    # Closing is idempotent.
    session.close()

    with pytest.raises(bridge.ZeroAppBindingError, match="closed"):
        asyncio.run(session.ainvoke({"app_name": "Pomodoro Focus"}))


def test_binding_imports_the_imported_source_snapshot_not_the_network() -> None:
    bridge = _load_bridge()

    assert (UNIT / "agent" / "zerodev" / "pipeline" / "factory_graph.py").is_file()
    assert bridge._SOURCE_ROOT == (UNIT / "agent").resolve()


def test_image_installs_the_runtime_gate_so_acceptance_is_reachable() -> None:
    """The headless-DOM gate must be present, or no app can ever be accepted.

    ``zerodev/pipeline/quality.py`` scores five dimensions. Two of them --
    ``charts`` (6) and ``records`` (18) -- are populated only from the runtime
    report in ``webview_app._collect_metrics``; they have no plan-derived
    fallback, unlike views/features/collections. With the gate skipped the
    runtime dimension also halves to 15 instead of 30, so the attainable total
    is 15 + 12 + 18 + 0 + 6 + 0 + 10 = 61 against ACCEPT_THRESHOLD = 70.

    Installing Node and jsdom is therefore not an optional convenience: without
    it the supervisor can only ever rework or reject, and a "reject" verdict
    would describe the image rather than the agent's behaviour.
    """

    dockerfile = (UNIT / "Dockerfile").read_text(encoding="utf-8")

    assert "node_modules" in dockerfile, "the harness dependency is not installed into the image"
    assert "tools/webverify" in dockerfile, "the harness path must match harness_available()"
    # jsdom 30 declares engines node ^22.22.2 || ^24.15.0 || >=26.0.0, and the
    # version is pinned in upstream's own package.json inside the read-only
    # snapshot, so the Node major has to satisfy it.
    assert "node:22" in dockerfile or "node:24" in dockerfile, (
        "Node must be >= 22.22 for jsdom 30; Debian's Node 18 would fail engines"
    )


def test_manifest_declares_the_upstream_revision_and_openai_route() -> None:
    """The manifest must pin upstream and route models through the interceptor."""

    import tomllib

    manifest = tomllib.loads((UNIT / "agent.toml").read_text(encoding="utf-8"))

    assert manifest["agent_id"] == "zeroapp"
    assert manifest["framework"] == "langgraph"
    assert manifest["source"]["method"] == "git"
    assert manifest["source"]["repository"] == "https://github.com/shodan1q/zeroapp"
    assert manifest["source"]["revision"] == "e081199fe9e9005715891860f43188e214acf163"
    assert manifest["adapter"]["binding"] == "bridge.py:create_graph"
    assert manifest["adapter"]["output_key"] == "answer"

    environment = manifest["llm_interception"]["environment"]
    # Upstream defaults to the Anthropic SDK path; the deployment must pin the
    # OpenAI-compatible provider so calls reach the intercepted route.
    assert environment["LLM_PROVIDER"] == "openai"
    assert environment["PIPELINE_CHECKPOINT_BACKEND"] == "memory"
    assert "OPENAI_API_KEY" not in environment

    route = manifest["llm_interception"]["routes"][0]
    assert route["host_patterns"] == ["api.openai.com"]
    assert route["path_patterns"] == ["/v1/chat/completions"]
    assert route["protocol_plugin"] == "openai-chat"
    assert route["credential"] == "openai"
    assert manifest["llm_interception"]["credentials"][0]["agent_env"] == "OPENAI_API_KEY"


def test_unit_is_registered_as_an_adapting_langgraph_agent() -> None:
    from agentbench.harness.registry import load_registry

    registry = load_registry(ROOT / "resources" / "registry.toml")
    registration = registry.find("zeroapp", enabled_only=False)

    assert Path(registration.path).resolve() == UNIT.resolve()
    assert registration.framework == "langgraph"
    # Onboarding lands as adapting and stays disabled until certified.
    assert registration.status == "adapting"
    assert registration.enabled is False
    assert registration.source == "https://github.com/shodan1q/zeroapp"
