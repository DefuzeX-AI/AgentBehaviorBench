"""Plugin discovery and composition-root behavior for evaluation SDKs."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from agentbench.cli.main import cli
from agentbench.harness import ProviderSelectionError
from agentbench.sdk.plugins import (
    SDK_ENTRY_POINT_GROUP,
    SDK_PLUGIN_API_VERSION,
    SDKReference,
    SDKRunnerContext,
    SDKSelection,
    evaluation_plan,
    installed_sdk_references,
    plugin_execution,
    resolve_sdk,
)


class FakeDistribution:
    def __init__(self, name: str, version: str) -> None:
        self.metadata = {"Name": name}
        self.version = version


class FakeEntryPoint:
    group = SDK_ENTRY_POINT_GROUP

    def __init__(
        self,
        name: str,
        value: str,
        distribution: str,
        loaded: object,
    ) -> None:
        self.name = name
        self.value = value
        self.dist = FakeDistribution(distribution, "2.1.0")
        self.loaded = loaded
        self.load_count = 0

    def load(self) -> object:
        self.load_count += 1
        return self.loaded


def fake_sdk() -> object:
    return SimpleNamespace(create_run=lambda **kwargs: None)


def test_listing_reads_metadata_without_loading_third_party_code() -> None:
    point = FakeEntryPoint("acme", "acme_eval:sdk", "acme-eval", fake_sdk())

    references = installed_sdk_references(entry_points_provider=lambda: (point,))

    acme = next(reference for reference in references if reference.name == "acme")
    assert acme.distribution == "acme-eval"
    assert acme.version == "2.1.0"
    assert acme.object_ref == "acme_eval:sdk"
    assert point.load_count == 0
    assert any(reference.name == "kuma" for reference in references)


def test_resolution_loads_only_the_selected_entry_point() -> None:
    selected = FakeEntryPoint("acme", "acme_eval:sdk", "acme-eval", fake_sdk())
    untouched = FakeEntryPoint("other", "other_eval:sdk", "other-eval", fake_sdk())

    result = resolve_sdk(
        "acme", entry_points_provider=lambda: (selected, untouched)
    )

    assert result.reference.qualified_name == "acme-eval::acme"
    assert result.value is selected.loaded
    assert selected.load_count == 1
    assert untouched.load_count == 0
    assert plugin_execution(result.value) == "local"


def test_distribution_qualifier_resolves_duplicate_names() -> None:
    first = FakeEntryPoint("judge", "one:sdk", "first-sdk", fake_sdk())
    second = FakeEntryPoint("judge", "two:sdk", "second_sdk", fake_sdk())

    with pytest.raises(ProviderSelectionError, match="ambiguous"):
        resolve_sdk("judge", entry_points_provider=lambda: (first, second))

    result = resolve_sdk(
        "second-sdk::judge", entry_points_provider=lambda: (first, second)
    )
    assert result.value is second.loaded
    assert first.load_count == 0
    assert second.load_count == 1


def test_explicit_python_import_is_marked_host_local() -> None:
    selection = resolve_sdk("python:examples.local_sdk")

    assert selection.reference.source == "python"
    assert selection.reference.object_ref == "examples.local_sdk"
    assert plugin_execution(selection.value) == "local"


def test_execution_plan_copies_options() -> None:
    options = {"difficulty": "bounded"}
    plan = evaluation_plan(sdk=fake_sdk(), options=options)
    options["difficulty"] = "changed"

    assert plan.options == {"difficulty": "bounded"}
    with pytest.raises(TypeError):
        plan.options["new"] = "value"  # type: ignore[index]


def test_plugin_api_version_is_checked_before_runner_creation() -> None:
    plugin = SimpleNamespace(
        name="bad",
        api_version="agentbench.evaluation_sdk.v999",
        execution="container",
        create_benchmark_runner=lambda **kwargs: None,
    )

    with pytest.raises(ProviderSelectionError, match="API version"):
        plugin_execution(plugin)


def test_builtin_kuma_is_an_explicit_container_plugin() -> None:
    selection = resolve_sdk("kuma")

    assert selection.reference.source == "builtin"
    assert plugin_execution(selection.value) == "container"
    assert selection.value.api_version == SDK_PLUGIN_API_VERSION


def test_cli_named_sdk_passes_a_selection_to_run(monkeypatch) -> None:
    calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        "agentbench.cli.features.run.run",
        lambda **kwargs: calls.append(kwargs) or 0,
    )

    assert cli(["run", "--sdk", "kuma"]) == 0
    selection = calls[0]["sdk_selection"]
    assert selection.reference.name == "kuma"  # type: ignore[union-attr]


def test_cli_sdk_list_displays_builtin_without_loading_plugins(
    monkeypatch, capsys
) -> None:
    reference = resolve_sdk("kuma").reference
    monkeypatch.setattr(
        "agentbench.cli.features.sdk.installed_sdk_references",
        lambda: (reference,),
    )

    assert cli(["sdk", "list"]) == 0
    output = capsys.readouterr().out
    assert "kuma\tbuiltin\tdefuzex-agentbench" in output
    assert SDK_ENTRY_POINT_GROUP in output


def test_deployable_plugin_shape_reports_its_locality() -> None:
    class Plugin:
        name = "acme"
        api_version = SDK_PLUGIN_API_VERSION
        execution = "container"

        def create_benchmark_runner(
            self, *, context: SDKRunnerContext, options: object
        ) -> object:
            del context, options
            return object()

    assert plugin_execution(Plugin()) == "container"


def test_runner_builder_delegates_to_the_selected_plugin(monkeypatch) -> None:
    from agentbench.sdk.runtime import build_evaluation_runner

    runner = SimpleNamespace(
        validate_sdk=lambda registration: "acme",
        run=lambda *args, **kwargs: None,
    )
    received: list[tuple[SDKRunnerContext, object]] = []

    class Plugin:
        name = "acme"
        api_version = SDK_PLUGIN_API_VERSION
        execution = "container"

        def create_benchmark_runner(
            self, *, context: SDKRunnerContext, options: object
        ) -> object:
            received.append((context, options))
            return runner

    plan = evaluation_plan(
        selection=SDKSelection(
            SDKReference("acme", "entry-point", "acme:plugin"), Plugin()
        ),
        options={"region": "test"},
    )
    monkeypatch.setenv("ABB_PLUGIN_TEST", "present")

    built = build_evaluation_runner(
        plan,
        model="test-model",
        trace_sink=object(),
        trace_max_bytes=4096,
    )

    assert built is runner
    assert received[0][0].environ["ABB_PLUGIN_TEST"] == "present"
    assert received[0][0].model == "test-model"
    assert received[0][1] == {"region": "test"}


def test_python_suite_runner_uses_the_same_plugin_factory() -> None:
    from agentbench.harness import SuiteRunner

    runner = SimpleNamespace(
        validate_sdk=lambda registration: "acme",
        run=lambda *args, **kwargs: None,
    )

    class Plugin:
        name = "acme"
        api_version = SDK_PLUGIN_API_VERSION
        execution = "container"

        def create_benchmark_runner(
            self, *, context: SDKRunnerContext, options: object
        ) -> object:
            del context
            assert options == {"region": "test"}
            return runner

    suite = SuiteRunner(
        sdk=Plugin(),  # type: ignore[arg-type]
        sdk_options={"region": "test"},
    )

    assert suite._benchmark_runner is runner
