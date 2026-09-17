"""Issue #57: host model target providers and framework adapters resolve through entry-point groups."""
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib
from dataclasses import dataclass
from importlib.metadata import EntryPoint
from pathlib import Path
from types import SimpleNamespace

import pytest

from agentbench.adapter import factory as adapter_factory
from agentbench.adapter.langgraph import LangGraphAdapter
from agentbench.harness.errors import ProviderSelectionError
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.interception import providers
from agentbench.runtime.interception.config import InterceptionConfigurationError
from agentbench.runtime.interception.providers import (
    MODEL_PROVIDER_ENTRY_POINT_GROUP,
    ModelTargetConfig,
    OpenRouterProvider,
    resolve_model_provider,
)
from agentbench.sdk.plugin.kuma.benchmark import KumaContainerRunner

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class FixtureProvider:
    model: str | None = None

    def resolve(self, environ):
        return ModelTargetConfig(provider_id='fixture', target_plugin='openrouter',
                                 base_url='https://fixture.invalid/v1',
                                 model=self.model or 'fixture-model', credential_env='FIXTURE_API_KEY')


class NotAProvider:
    def __init__(self, model=None):
        self.model = model


class FixtureAdapter:
    def __init__(self, path):
        self.path = path

    @classmethod
    def from_agent_dir(cls, path):
        return cls(path)

    @property
    def is_loaded(self):
        return False

    def load(self):
        return self

    def invoke(self, value, *, run_config=None):
        raise NotImplementedError

    async def ainvoke(self, value, *, run_config=None):
        raise NotImplementedError

    def close(self):
        pass


def _install(monkeypatch, module, group, **targets):
    points = [EntryPoint(name, f'{__name__}:{target}', group) for name, target in targets.items()]
    monkeypatch.setattr(module, 'entry_points',
                        lambda *, group: [point for point in points if point.group == group])


def test_default_provider_is_the_built_in_openrouter(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP)
    assert resolve_model_provider(environ={}) == OpenRouterProvider()
    assert resolve_model_provider(model='vendor/model', environ={}) == OpenRouterProvider(model='vendor/model')


def test_environment_selects_a_registered_provider(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP, fixture='FixtureProvider')
    provider = resolve_model_provider(model='chosen', environ={'ABB_MODEL_PROVIDER': ' Fixture '})
    assert provider == FixtureProvider(model='chosen')
    assert provider.resolve({}).base_url == 'https://fixture.invalid/v1'


def test_explicit_name_wins_over_environment(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP, fixture='FixtureProvider')
    assert isinstance(resolve_model_provider('openrouter', environ={'ABB_MODEL_PROVIDER': 'fixture'}),
                      OpenRouterProvider)


def test_unknown_provider_names_the_available_ones(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP, fixture='FixtureProvider')
    with pytest.raises(InterceptionConfigurationError,
                       match=r"Unknown model target provider 'missing'; available: fixture, openrouter"):
        resolve_model_provider(environ={'ABB_MODEL_PROVIDER': 'missing'})


def test_plugin_cannot_replace_the_built_in_name(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP, openrouter='FixtureProvider')
    assert isinstance(resolve_model_provider(environ={}), OpenRouterProvider)


def test_factory_without_resolve_is_rejected(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP, broken='NotAProvider')
    with pytest.raises(InterceptionConfigurationError, match='does not implement resolve'):
        resolve_model_provider('broken', environ={})


def test_docker_runtime_constructs_the_selected_provider(monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP, fixture='FixtureProvider')
    runtime = DockerRuntime(environ={'ABB_MODEL_PROVIDER': 'fixture'})
    assert runtime._model_provider == FixtureProvider()


def test_kuma_configuration_check_rejects_an_unknown_provider_before_any_case(tmp_path, monkeypatch):
    _install(monkeypatch, providers, MODEL_PROVIDER_ENTRY_POINT_GROUP)
    (tmp_path / 'requirement.md').write_text('profile')
    runner = KumaContainerRunner(environ={'KUMA_API_KEY': 'preflight-placeholder',
                                         'ABB_MODEL_PROVIDER': 'does-not-exist'})
    with pytest.raises(ProviderSelectionError, match="Unknown model target provider 'does-not-exist'"):
        runner.validate_sdk(SimpleNamespace(path=tmp_path))


def test_adapter_resolves_from_the_entry_point_group(monkeypatch, tmp_path):
    _install(monkeypatch, adapter_factory, 'group', custom='FixtureAdapter')
    factory = adapter_factory.AdapterFactory({'langgraph': LangGraphAdapter.from_agent_dir},
                                             entry_point_group='group')
    assert factory.frameworks() == ('custom', 'langgraph')
    adapter = factory.create(SimpleNamespace(framework='Custom', path=tmp_path))
    assert isinstance(adapter, FixtureAdapter) and adapter.path == tmp_path


def test_unknown_framework_lists_entry_point_frameworks(monkeypatch, tmp_path):
    _install(monkeypatch, adapter_factory, 'group', custom='FixtureAdapter')
    factory = adapter_factory.AdapterFactory({'langgraph': LangGraphAdapter.from_agent_dir},
                                             entry_point_group='group')
    with pytest.raises(adapter_factory.UnsupportedAdapterError, match='supported: custom, langgraph'):
        factory.create(SimpleNamespace(framework='crewai', path=tmp_path))


def test_built_in_adapter_survives_without_distribution_metadata(monkeypatch):
    # The evaluation container runs ABB from source, where no entry points exist.
    _install(monkeypatch, adapter_factory, adapter_factory.ADAPTER_ENTRY_POINT_GROUP)
    assert adapter_factory.DEFAULT_ADAPTER_FACTORY.frameworks() == ('langgraph',)


def test_distribution_declares_both_groups_for_the_built_ins():
    groups = tomllib.loads((ROOT / 'pyproject.toml').read_text())['project']['entry-points']
    provider = groups[MODEL_PROVIDER_ENTRY_POINT_GROUP]['openrouter']
    adapter = groups[adapter_factory.ADAPTER_ENTRY_POINT_GROUP]['langgraph']
    assert EntryPoint('openrouter', provider, MODEL_PROVIDER_ENTRY_POINT_GROUP).load() is OpenRouterProvider
    assert EntryPoint('langgraph', adapter, adapter_factory.ADAPTER_ENTRY_POINT_GROUP).load() is LangGraphAdapter
