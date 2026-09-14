"""Directory discovery and the shared SDK interface, independent of SDK vendors."""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest

import agentbench.sdk.plugin as sdk_package
from agentbench.cli.main import cli
from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk import discovery
from agentbench.sdk.plugins import evaluation_plan, plugin_execution, resolve_sdk
from agentbench.sdk.runtime import build_evaluation_runner


MINIMAL_PLUGIN = """
from types import SimpleNamespace
from agentbench.sdk.contracts import PreparedCase
class Adapter:
    execution = 'local'
    def create_benchmark_runner(self, *, context, options):
        return SimpleNamespace(
            validate_sdk=lambda registration: 'test',
            prepare_cases=lambda registration, **kwargs: tuple(PreparedCase(i) for i in range(registration.case_count)),
            run_case=lambda registration, case, **kwargs: None,
            context=context, options=options)
plugin = Adapter()
"""


def test_plugin_needs_explicit_case_concurrency_capabilities(adapter_directory):
    from agentbench.sdk.contracts import SDKRunnerContext
    from agentbench.sdk.runtime import build_evaluation_runner_factory

    add_adapter(adapter_directory)
    factory = build_evaluation_runner_factory(
        evaluation_plan(), model=None, trace_sink=None, trace_max_bytes=1024, environ={},
    )
    assert factory.supports_concurrency is False
    # Optional concurrency fields do not change directory discovery's protocol.
    context = SDKRunnerContext(environ={}, model=None, trace_sink=None, trace_max_bytes=1024)
    assert context.control is None and context.runtime_services is None


def test_factory_freezes_environment_and_renews_services_each_suite(adapter_directory, monkeypatch):
    from agentbench.runtime.contracts.execution import RunControl
    from agentbench.sdk.runtime import build_evaluation_runner_factory

    add_adapter(adapter_directory)
    environment = {'OPENROUTER_MODEL': 'snapshot', 'KUMA_API_KEY': 'captured-secret'}
    factory = build_evaluation_runner_factory(
        evaluation_plan(), model=None, trace_sink=None, trace_max_bytes=1024,
        environ=environment,
    )
    environment['OPENROUTER_MODEL'] = 'changed'
    monkeypatch.setenv('OPENROUTER_MODEL', 'process-change')
    first = factory.open_suite('first-suite', RunControl())
    second = factory.open_suite('second-suite', RunControl())
    a = first.create(SimpleNamespace(agent_id='a'), {'job_id': 'job-a'})
    b = first.create(SimpleNamespace(agent_id='b'), {'job_id': 'job-b'})
    rerun = second.create(SimpleNamespace(agent_id='a'), {'job_id': 'rerun-a'})
    assert a is not b
    assert a.context.environ['OPENROUTER_MODEL'] == 'snapshot'
    assert a.context.job_context == {'suite_id': 'first-suite', 'job_id': 'job-a', 'agent_id': 'a'}
    assert a.context.build_coordinator is b.context.build_coordinator
    assert a.context.build_coordinator is not rerun.context.build_coordinator
    assert a.context.control is not rerun.context.control
    with pytest.raises(TypeError):
        a.context.environ['OPENROUTER_MODEL'] = 'cannot-mutate'
    first.close()
    first.close()
    second.close()
    with pytest.raises(RuntimeError, match='closed'):
        first.create(SimpleNamespace(agent_id='c'), {'job_id': 'job-c'})

CASE_FILE_PLUGIN = """
class Adapter:
    execution = 'local'
    def create_benchmark_runner(self, *, context, options):
        from agentbench.harness import BenchmarkRunner
        from examples import case_file_sdk
        return BenchmarkRunner(sdk=case_file_sdk, sdk_options=options)
plugin = Adapter()
"""


@pytest.fixture
def adapter_directory(tmp_path, monkeypatch):
    """Isolate real package imports without adding SDKs to the production tree."""
    root = tmp_path / "sdk" / "plugin"
    root.mkdir(parents=True)
    original_modules = set(sys.modules)
    original_attributes = set(vars(sdk_package))
    monkeypatch.setattr(discovery, "SDK_ROOT", root)
    monkeypatch.setattr(sdk_package, "__path__", [str(root)])
    yield root
    for name in set(sys.modules) - original_modules:
        if name.startswith("agentbench.sdk.plugin."):
            sys.modules.pop(name, None)
    for name in set(vars(sdk_package)) - original_attributes:
        delattr(sdk_package, name)
    importlib.invalidate_caches()


def add_adapter(root, name="alpha", source=MINIMAL_PLUGIN, initializer=""):
    directory = root / name
    directory.mkdir()
    (directory / "__init__.py").write_text(initializer, encoding="utf-8")
    (directory / "plugin.py").write_text(source, encoding="utf-8")
    importlib.invalidate_caches()
    return directory


def test_listing_is_sorted_relative_to_package_and_does_not_import(
    adapter_directory, monkeypatch, tmp_path
):
    for name in ("zeta", "alpha"):
        add_adapter(
            adapter_directory,
            name,
            initializer='raise AssertionError("must not import")',
        )
    (adapter_directory / "common").mkdir()
    (adapter_directory / "not_an_adapter.py").write_text("")
    add_adapter(adapter_directory, "_private")
    monkeypatch.chdir(tmp_path.parent)
    references = discovery.discover_sdks()
    assert [item.name for item in references] == ["alpha", "zeta"]
    assert references[0].object_ref == "agentbench.sdk.plugin.alpha.plugin:plugin"
    assert all(item.source == "directory" for item in references)
    assert "agentbench.sdk.plugin.alpha" not in sys.modules


def test_adding_directory_changes_availability_without_registration(adapter_directory):
    add_adapter(adapter_directory)
    assert resolve_sdk().reference.name == "alpha"
    add_adapter(adapter_directory, "beta")
    assert [item.name for item in discovery.discover_sdks()] == ["alpha", "beta"]
    with pytest.raises(ProviderSelectionError, match="Multiple SDK adapters"):
        evaluation_plan()
    assert resolve_sdk(" BETA ").reference.name == "beta"
    (adapter_directory / "alpha" / "plugin.py").unlink()
    assert resolve_sdk().reference.name == "beta"
    with pytest.raises(ProviderSelectionError, match="Unknown SDK"):
        resolve_sdk("alpha")  # Previously imported modules do not bypass discovery.


def test_sdk_siblings_are_outside_the_scanned_plugin_directory(adapter_directory):
    add_adapter(adapter_directory.parent, "outside")
    add_adapter(adapter_directory, "inside")
    assert [item.name for item in discovery.discover_sdks()] == ["inside"]
    assert resolve_sdk().reference.object_ref == "agentbench.sdk.plugin.inside.plugin:plugin"
    with pytest.raises(ProviderSelectionError, match="Unknown SDK"):
        resolve_sdk("outside")


def test_no_adapters_has_actionable_error_and_empty_cli_list(adapter_directory, capsys):
    with pytest.raises(ProviderSelectionError, match="No SDK adapters found"):
        resolve_sdk()
    assert cli(["sdk", "list"]) == 0
    assert "No SDK adapters found" in capsys.readouterr().out


@pytest.mark.parametrize(
    "name", ["kuma", "panda", "python:os", "os:path", "vendor::alpha", "../alpha", "os"]
)
def test_unknown_name_never_falls_back_to_import_or_special_sdk(
    adapter_directory, name
):
    add_adapter(adapter_directory)
    with pytest.raises(ProviderSelectionError, match="Unknown SDK"):
        resolve_sdk(name)


@pytest.mark.parametrize("name", ["", "  "])
def test_empty_name_is_not_automatic_selection(adapter_directory, name):
    add_adapter(adapter_directory)
    with pytest.raises(ProviderSelectionError, match="cannot be empty"):
        resolve_sdk(name)


@pytest.mark.parametrize("name", ["invalid-name", "for", "123sdk"])
def test_invalid_directory_name_is_reported(adapter_directory, name):
    add_adapter(adapter_directory, name)
    with pytest.raises(ProviderSelectionError, match="Invalid SDK directory name"):
        discovery.discover_sdks()


def test_missing_package_initializer_is_reported(adapter_directory):
    directory = add_adapter(adapter_directory)
    (directory / "__init__.py").unlink()
    with pytest.raises(ProviderSelectionError, match="missing __init__.py"):
        discovery.discover_sdks()


def test_missing_dependency_does_not_break_listing_or_other_adapter(
    adapter_directory, capsys
):
    add_adapter(adapter_directory)
    add_adapter(adapter_directory, "broken", "import abb_nonexistent_sdk_dependency\n")
    assert cli(["sdk", "list"]) == 0
    assert "broken\tdirectory" in capsys.readouterr().out
    assert resolve_sdk("alpha").reference.name == "alpha"
    with pytest.raises(
        ProviderSelectionError, match="abb_nonexistent_sdk_dependency"
    ) as error:
        resolve_sdk("broken")
    assert isinstance(error.value.__cause__, ModuleNotFoundError)
    assert cli(["sdk", "show", "broken"]) == 2


@pytest.mark.parametrize(
    "source, message",
    [
        ("plugin = object()", "plugin instance"),
        ('plugin = type("Adapter", (), {})', "plugin instance"),
        (
            "from types import SimpleNamespace\nplugin = SimpleNamespace(create_run=lambda: None)",
            "plugin instance",
        ),
        ('raise RuntimeError("private-settings")', "RuntimeError"),
        ("other_export = None", "plugin export"),
        (MINIMAL_PLUGIN + "\nplugin.execution = []", "execution mode"),
        (
            MINIMAL_PLUGIN + "\nplugin.create_benchmark_runner = 42",
            "create_benchmark_runner",
        ),
    ],
)
def test_invalid_plugins_fail_before_runner_creation(
    adapter_directory, source, message
):
    add_adapter(adapter_directory, source=source)
    with pytest.raises(ProviderSelectionError, match=message) as error:
        resolve_sdk()
    assert "private-settings" not in str(error.value)


def test_cli_and_python_resolve_the_same_adapter(
    adapter_directory, monkeypatch, capsys
):
    add_adapter(adapter_directory)
    selected = evaluation_plan().selection
    calls = []
    monkeypatch.setattr(
        "agentbench.cli.features.run.run", lambda config: calls.append(config) or 0
    )
    assert cli(["run", "--sdk", "alpha"]) == 0
    assert calls[0].sdk_selection.value is selected.value
    assert cli(["sdk", "show", "alpha"]) == 0
    assert "Execution: local" in capsys.readouterr().out
    assert cli(["run", "--sdk", "unknown"]) == 2
    assert len(calls) == 1


def test_factory_receives_context_and_readonly_copied_options(
    adapter_directory, monkeypatch
):
    add_adapter(adapter_directory)
    options = {"region": "test"}
    plan = evaluation_plan(options=options)
    options["region"] = "changed"
    sink = object()
    monkeypatch.setenv("ABB_SDK_TEST_CONTEXT", "present")
    runner = build_evaluation_runner(
        plan, model="test-model", trace_sink=sink, trace_max_bytes=99
    )
    assert runner.options == {"region": "test"}
    assert runner.context.model == "test-model"
    assert runner.context.trace_sink is sink
    assert runner.context.trace_max_bytes == 99
    assert runner.context.environ["ABB_SDK_TEST_CONTEXT"] == "present"
    with pytest.raises(TypeError):
        runner.options["region"] = "modified"


def test_invalid_runner_is_rejected(adapter_directory):
    add_adapter(
        adapter_directory,
        source=MINIMAL_PLUGIN
        + "\nplugin.create_benchmark_runner = lambda **kw: object()",
    )
    with pytest.raises(ProviderSelectionError, match="invalid runner"):
        build_evaluation_runner(
            evaluation_plan(), model=None, trace_sink=object(), trace_max_bytes=99
        )


def test_agent_loop_only_runner_is_not_a_case_runner(adapter_directory):
    add_adapter(adapter_directory, source=MINIMAL_PLUGIN + '''
plugin.create_benchmark_runner = lambda **kw: SimpleNamespace(
    validate_sdk=lambda registration: 'test', run=lambda registration, **kw: None)
''')
    with pytest.raises(ProviderSelectionError, match='invalid runner'):
        build_evaluation_runner(evaluation_plan(), model=None, trace_sink=None, trace_max_bytes=1024)


def test_prepared_case_is_immutable_and_validates_explicit_artifact_identity(tmp_path):
    from dataclasses import FrozenInstanceError
    from agentbench.sdk.contracts import PreparedCase

    case = PreparedCase(0, 'case', tmp_path / 'case.json', 'a' * 64, 'b' * 64)
    assert case.content_sha256 != case.artifact_sha256
    with pytest.raises(FrozenInstanceError):
        case.case_index = 1
    for value in (-1, True, 1.5):
        with pytest.raises(ValueError, match='case_index'):
            PreparedCase(value)
    with pytest.raises(ValueError, match='absolute'):
        PreparedCase(0, artifact_path=Path('relative.json'))
    with pytest.raises(ValueError, match='artifact_sha256'):
        PreparedCase(0, artifact_sha256='not-a-hash')


def test_generic_case_preparation_never_creates_sdk_runs():
    from agentbench.harness import BenchmarkRunner

    sdk = SimpleNamespace(create_run=lambda **kwargs: pytest.fail('Preparation must not create an SDK Run'))
    cases = BenchmarkRunner(sdk=sdk).prepare_cases(SimpleNamespace(case_count=3))
    assert tuple(case.case_index for case in cases) == (0, 1, 2)
    assert all(case.artifact_path is None for case in cases)


def test_lazy_sdk_dependency_error_identifies_selected_adapter(adapter_directory):
    add_adapter(
        adapter_directory,
        source=MINIMAL_PLUGIN
        + "\ndef create(**kwargs):\n    import abb_missing_lazy_dependency\n"
        + "plugin.create_benchmark_runner = create\n",
    )
    plan = evaluation_plan()  # Listing and selection do not need this dependency.
    with pytest.raises(
        ProviderSelectionError, match="alpha.*abb_missing_lazy_dependency"
    ):
        build_evaluation_runner(
            plan, model=None, trace_sink=object(), trace_max_bytes=99
        )


def test_python_injection_does_not_need_a_directory(adapter_directory):
    sdk = SimpleNamespace(create_run=lambda **kwargs: None)
    plan = evaluation_plan(sdk=sdk)
    assert plan.selection.value is sdk
    assert plan.selection.reference.source == "python"
    assert discovery.discover_sdks() == ()
    with pytest.raises(ValueError, match="not both"):
        evaluation_plan(sdk=sdk, selection=plan.selection)


def test_invalid_adapter_does_not_fall_back_to_create_run():
    sdk = SimpleNamespace(create_run=lambda: None, execution="local")
    with pytest.raises(ProviderSelectionError, match="create_benchmark_runner"):
        plugin_execution(sdk)


def test_low_level_runner_has_no_implicit_vendor_default():
    from agentbench.harness import BenchmarkRunner

    runner = BenchmarkRunner()
    with pytest.raises(ProviderSelectionError, match="explicit SDK object"):
        runner.validate_sdk(None)
    with pytest.raises(ProviderSelectionError, match="explicit SDK object"):
        runner.run(None)


def test_contracts_import_without_harness_discovery_or_evaluators():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from agentbench.sdk import SDK, EvaluationSDKPlugin, SDKReference
assert 'agentbench.sdk.discovery' not in sys.modules
assert 'agentbench.sdk.plugins' not in sys.modules
assert 'agentbench.harness' not in sys.modules
assert 'kuma' not in sys.modules and 'defuzex' not in sys.modules
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_production_discovery_does_not_import_adapter_modules():
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            """
import sys
from agentbench.sdk import discover_sdks
for reference in discover_sdks():
    assert 'agentbench.sdk.plugin.' + reference.name not in sys.modules
    assert reference.object_ref.partition(':')[0] not in sys.modules
""",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr


def test_discovered_adapter_runs_real_agent_and_exports_case_output_judge(
    adapter_directory, tmp_path, monkeypatch
):
    from agentbench.cli.execution import run_benchmark_session
    from agentbench.cli.trace_runtime import build_trace_suite_runner
    from agentbench.harness import AgentRegistration

    add_adapter(adapter_directory, source=CASE_FILE_PLUGIN)
    agent_root = tmp_path / "echo"
    source = agent_root / "agent"
    source.mkdir(parents=True)
    module_name = f"sdk_directory_echo_{uuid4().hex}"
    (source / f"{module_name}.py").write_text(
        "from typing_extensions import TypedDict\n"
        "from langgraph.graph import StateGraph, START, END\n"
        "class State(TypedDict):\n    prompt: str\n    response: str\n"
        "builder = StateGraph(State)\n"
        'builder.add_node("echo", lambda state: {"response": state["prompt"]})\n'
        'builder.add_edge(START, "echo")\nbuilder.add_edge("echo", END)\n'
        "graph = builder.compile()\n",
        encoding="utf-8",
    )
    (source / "langgraph.json").write_text(
        json.dumps({"graphs": {"agent": f"./{module_name}.py:graph"}})
    )
    (agent_root / "agent.toml").write_text(
        '[adapter]\ntype="langgraph"\nmode="in_process"\nconfig="langgraph.json"\n'
        'graph_id="agent"\ninput_key="prompt"\noutput_key="response"\n'
    )
    agent = AgentRegistration(
        "echo", agent_root, True, "ready", "langgraph", "test", case_count=2
    )
    case = tmp_path / "case.json"
    case.write_text(
        json.dumps(
            {
                "inputs": [
                    {"input_id": "one", "payload": "hello", "expected_output": "hello"}
                ]
            }
        )
    )
    options = {"case_file": str(case)}
    runner = build_trace_suite_runner(max_bytes=100, sdk_options=options)
    execution = run_benchmark_session(
        (agent,),
        runner=runner,
        output_path=tmp_path / "result.json",
        output_fn=lambda _: None,
        viewer_starter=None,
    )
    assert execution.exit_code == 0
    benchmarks = execution.result.items[0].benchmarks
    assert len(benchmarks) == 2
    assert benchmarks[0].run_id != benchmarks[1].run_id
    assert all(result.report.status == "pass" for result in benchmarks)
    assert benchmarks[0].steps[0].invocation.output == "hello"
    data = json.loads(execution.result_log.path.read_text(encoding="utf-8"))
    assert any(event["event"] == "step_completed" for event in data)
    assert data[-1]["event"] == "suite_completed"

    # The real evaluate command uses the same discovered adapter and exporter.
    from agentbench.cli.features import evaluate

    monkeypatch.setattr(evaluate, "enabled_agents", lambda _: [{"agent_id": "echo"}])
    monkeypatch.setattr(evaluate, "resolve_agent", lambda *_: agent)
    monkeypatch.setattr(evaluate, "load_project_environment", lambda _: None)
    options_file = tmp_path / "options.json"
    options_file.write_text(json.dumps(options))
    assert (
        cli(
            [
                "evaluate",
                "echo",
                "--sdk",
                "alpha",
                "--sdk-options",
                str(options_file),
                "--no-view",
                "--yes",
                "--result-output",
                str(tmp_path / "cli-result.json"),
            ]
        )
        == 0
    )


@pytest.mark.skipif(
    not os.getenv("ABB_SDK_DOCKER_IMAGE"), reason="Opt-in offline real KUMA container"
)
def test_directory_adapter_retains_real_container_run(adapter_directory):
    from agentbench.cli.execution import run_benchmark_session
    from agentbench.cli.trace_runtime import build_trace_suite_runner
    from agentbench.harness import AgentRegistration

    fixtures = Path(__file__).parent / "sdk_fixtures"
    add_adapter(
        adapter_directory,
        "container_check",
        (fixtures / "container_plugin.py").read_text(),
    )
    output = (
        Path(__file__).resolve().parents[1]
        / "results/verification"
        / f"sdk-directory-{uuid4().hex}"
    )
    runner = build_trace_suite_runner(
        max_bytes=1024,
        sdk_options={
            "image": os.environ["ABB_SDK_DOCKER_IMAGE"],
            "fixtures": str(fixtures),
            "output": str(output),
        },
    )
    agent = AgentRegistration(
        "offline-echo", fixtures, True, "ready", "fixture", "acceptance", case_count=2,
    )
    execution = run_benchmark_session(
        (agent,),
        runner=runner,
        output_path=output / "suite.json",
        output_fn=print,
        viewer_starter=None,
    )
    assert execution.exit_code == 0, f"See {output}"
    run_ids = []
    for case_index in range(agent.case_count):
        directory = output / f'case-{case_index:04d}'
        for name in ("case.json", "agent-output.json", "judge.json", "run.json"):
            assert (directory / name).is_file()
        run = json.loads((directory / "run.json").read_text())
        assert run["report"]["status"] == "pass"
        assert run["provider_mode"] == "offline-custom"
        assert run["network"] == "none"
        run_ids.append(run['run_id'])
    assert len(set(run_ids)) == agent.case_count
    assert execution.result_log.path.is_file()
    print(f"Acceptance artifacts retained: {output}")
