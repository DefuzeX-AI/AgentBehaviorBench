"""Suite recovery compares the model configuration actually used by each consumer."""
import json

import pytest

from agentbench.cli.sessions.configuration import build_saved_runner, runner_configuration
from agentbench.cli.trace_runtime import build_trace_suite_runner
from agentbench.harness.registry import AgentRegistration
from agentbench.harness.session.plan import build_plan, validate_provenance, SuiteProvenanceError
from agentbench.sdk.plugins import resolve_sdk


ENV = {'GLM_API_KEY': 'glm-secret-value', 'GLM_MODEL': 'glm-original',
       'GLM_API_BASE_URL': 'https://native.example/v1',
       'OPENROUTER_API_KEY': 'router-secret-value', 'OPENROUTER_MODEL': 'unused-model'}


def agent(tmp_path, framework='acp', suffix='', fixed_model=None):
    root = tmp_path / (framework + suffix)
    root.mkdir()
    manifest = f'''schema_version = "defuzex-bench.agent.v2"
framework = "{framework}"
[runtime]
env_keys = ["GLM_MODEL", "GLM_API_BASE_URL", "GLM_API_KEY", "PRIVATE_AUTH"]
secret_env_keys = ["GLM_API_KEY", "PRIVATE_AUTH"]
[llm_interception]
trust_plugin = "pem-env"
credentials = [{{id = "native", agent_env = "OPENAI_API_KEY", auth_plugin = "bearer-token"}}]
routes = []
'''
    if framework == 'acp':
        manifest += '\n[model]\nprovider = "glm"\nsource = "native"\n'
    if fixed_model:
        manifest += f'\n[llm_interception.environment]\nGLM_MODEL = "{fixed_model}"\n'
    (root / 'agent.toml').write_text(manifest)
    return AgentRegistration(root.name, root, True, 'ready', framework, 'fixture')


def configuration(agents, env, *, sdk='kuma', model=None):
    runner = build_trace_suite_runner(max_bytes=4096, environ=env, model=model,
                                     sdk_selection=resolve_sdk(sdk))
    return runner_configuration(runner, agents)


def resume(agents, before, after, *, sdk='kuma', model=None):
    config = configuration(agents, before, sdk=sdk, model=model)
    plan = build_plan('suite_issue155', agents, configuration=config)
    restored = build_saved_runner(plan['configuration'], after)
    current = runner_configuration(restored, agents)
    validate_provenance(plan, agents, current)
    return plan, current


@pytest.mark.parametrize('change', [
    {'OPENROUTER_BASE_URL': 'https://unused.example/v1'},
    {'OPENROUTER_MODEL': 'unused-new-model'},
    {'ABB_MODEL_PROVIDER': 'does-not-exist', 'ABB_MODEL_ROUTING_CONFIG': 'missing.toml'},
])
def test_observe_ignores_unused_replacement_settings(tmp_path, change):
    agents = [agent(tmp_path)]
    resume(agents, ENV, {**ENV, **change})


@pytest.mark.parametrize('with_router', [False, True])
@pytest.mark.parametrize('change', [
    {'GLM_MODEL': 'different-model'},
    {'GLM_API_BASE_URL': 'https://different.example/v1'},
])
def test_native_changes_reject_resume(tmp_path, with_router, change):
    agents = [agent(tmp_path)]
    env = {k: v for k, v in ENV.items() if with_router or not k.startswith('OPENROUTER_')}
    with pytest.raises(SuiteProvenanceError):
        resume(agents, env, {**env, **change})


def test_observe_records_declared_public_settings_and_excludes_credentials(tmp_path):
    agents = [agent(tmp_path)]
    env = {**ENV, 'PRIVATE_AUTH': 'private-secret-value'}
    plan, current = resume(agents, env, {**env, 'GLM_API_KEY': 'rotated-secret',
                                      'PRIVATE_AUTH': 'rotated-private'})
    native = current['agent_models'][agents[0].agent_id]
    assert native['mode'] == 'observe'
    assert native['runtime_settings'] == {k: ENV[k] for k in ('GLM_MODEL', 'GLM_API_BASE_URL')}
    serialized = json.dumps(plan)
    assert all(value not in serialized for key, value in env.items() if 'KEY' in key or key == 'PRIVATE_AUTH')
    assert current['provider_base_url'] is None


def test_manifest_override_matches_actual_native_environment(tmp_path):
    agents = [agent(tmp_path, fixed_model='fixed-model')]
    _, current = resume(agents, ENV, {**ENV, 'GLM_MODEL': 'ignored-change'})
    assert current['agent_models'][agents[0].agent_id]['runtime_settings']['GLM_MODEL'] == 'fixed-model'


def test_replace_re_resolves_defaults_but_preserves_explicit_cli_override(tmp_path):
    agents = [agent(tmp_path, 'langgraph')]
    changed = {**ENV, 'OPENROUTER_MODEL': 'new-model'}
    with pytest.raises(SuiteProvenanceError):
        resume(agents, ENV, changed)
    _, current = resume(agents, ENV, changed, model='cli-model')
    assert current['model'] == current['model_override'] == 'cli-model'
    with pytest.raises(SuiteProvenanceError):
        resume(agents, ENV, {**ENV, 'OPENROUTER_BASE_URL': 'https://new.example/v1'}, model='cli-model')


def test_mixed_suite_checks_both_consumers(tmp_path):
    agents = [agent(tmp_path), agent(tmp_path, 'langgraph')]
    for change in ({'GLM_MODEL': 'new-native'}, {'OPENROUTER_MODEL': 'new-replacement'}):
        with pytest.raises(SuiteProvenanceError):
            resume(agents, ENV, {**ENV, **change})


def test_local_judge_is_checked_independently_from_observe_agent(tmp_path):
    agents = [agent(tmp_path)]
    with pytest.raises(SuiteProvenanceError):
        resume(agents, ENV, {**ENV, 'OPENROUTER_MODEL': 'new-judge'}, sdk='local')
    env = {**ENV, 'ABB_LOCAL_JUDGE_MODEL': 'judge-model',
           'ABB_LOCAL_JUDGE_BASE_URL': 'https://judge.example/v1',
           'ABB_LOCAL_JUDGE_API_KEY': 'judge-secret-value'}
    plan, current = resume(agents, env, {**env, 'OPENROUTER_MODEL': 'irrelevant',
                                      'ABB_LOCAL_JUDGE_API_KEY': 'rotated-judge'}, sdk='local')
    assert current['sdk_configuration']['judge']['model'] == 'judge-model'
    assert 'judge-secret-value' not in json.dumps(plan)
    with pytest.raises(SuiteProvenanceError):
        resume(agents, env, {**env, 'ABB_LOCAL_JUDGE_MODEL': 'changed'}, sdk='local')


def test_custom_entry_point_target_is_recorded(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from agentbench.runtime.interception import providers

    class CustomProvider:
        def __init__(self, model=None):
            self.model = model

        def resolve(self, environ):
            return providers.ModelTargetConfig('custom', 'compatible-json',
                environ['CUSTOM_URL'], self.model or environ.get('ABB_MODEL') or environ['CUSTOM_MODEL'], 'CUSTOM_KEY')

    monkeypatch.setattr(providers, 'entry_points', lambda **kwargs: [
        SimpleNamespace(name='custom', load=lambda: CustomProvider)])
    agents = [agent(tmp_path, 'langgraph')]
    env = {**ENV, 'ABB_MODEL_PROVIDER': 'custom', 'CUSTOM_URL': 'https://custom.example/v1',
           'CUSTOM_MODEL': 'custom-model', 'CUSTOM_KEY': 'custom-secret'}
    _, current = resume(agents, env, {**env, 'OPENROUTER_BASE_URL': 'https://unused.example'})
    assert current['provider_base_url'] == env['CUSTOM_URL']
    assert current['model'] == 'custom-model'
    from agentbench.sdk.plugins import evaluation_plan
    from agentbench.sdk.runtime import build_evaluation_runner
    actual_runner = build_evaluation_runner(evaluation_plan(selection=resolve_sdk('kuma')),
        model='cli-custom', trace_sink=None, trace_max_bytes=4096, environ=env)
    actual_target = providers.resolve_model_provider(environ=actual_runner.environ).resolve(actual_runner.environ)
    configured = configuration(agents, env, model='cli-custom')
    assert configured['model'] == actual_target.model == 'cli-custom'
    with pytest.raises(SuiteProvenanceError):
        resume(agents, env, {**env, 'CUSTOM_MODEL': 'changed'})


def test_routing_file_contents_are_part_of_provenance(tmp_path):
    agents = [agent(tmp_path, 'langgraph')]
    routing = tmp_path / 'routing.toml'
    contents = '''[targets.text]
provider = "glm"
model = "route-model"
[[rules]]
id = "text"
target = "text"
protocols = ["openai-chat"]
input = "text"
'''
    routing.write_text(contents)
    env = {**ENV, 'ABB_MODEL_ROUTING_CONFIG': str(routing)}
    config = configuration(agents, env)
    plan = build_plan('suite_routing', agents, configuration=config)
    # An explicit routing file does not use the default run target.
    resume(agents, env, {**env, 'OPENROUTER_MODEL': 'irrelevant'})
    routing.write_text(contents.replace('route-model', 'new-route-model'))
    restored = build_saved_runner(plan['configuration'], env)
    with pytest.raises(SuiteProvenanceError):
        validate_provenance(plan, agents, runner_configuration(restored, agents))


def test_recovery_entry_rejects_native_model_change_before_execution(tmp_path):
    from agentbench.cli.sessions.recovery import execute_in_store
    from agentbench.harness.session import SuiteStore
    agents = [agent(tmp_path)]
    config = configuration(agents, ENV)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_recovery', agents, configuration=config, environ=ENV) as store:
        with pytest.raises(SuiteProvenanceError):
            execute_in_store(store, environ={**ENV, 'GLM_MODEL': 'changed'})


def test_reuse_subset_recomputes_provenance_and_preserves_requested_override(tmp_path, monkeypatch):
    from agentbench.cli.sessions import reuse
    from agentbench.harness.session import SuiteStore
    from tests.test_suite_resume import make_case
    monkeypatch.setattr(reuse, 'PROJECT_ROOT', tmp_path)
    agents = [agent(tmp_path), agent(tmp_path, 'langgraph')]
    config = configuration(agents, ENV)
    with SuiteStore.begin(tmp_path / 'suites', 'suite_source', agents, configuration=config, environ=ENV) as store:
        for index, registration in enumerate(agents):
            store.retain_case(registration.agent_id, make_case(tmp_path / str(index), 0))
        source = store.directory
    for selected in agents:
        inputs = reuse.reuse_inputs(source, environ=ENV, model='explicit-new',
                                    selection={(selected.agent_id, 0)})
        assert set(inputs.configuration['agent_models']) == {selected.agent_id}
        assert inputs.configuration['model_override'] == 'explicit-new'
        restored = build_saved_runner(inputs.configuration, ENV)
        assert runner_configuration(restored, inputs.registrations) == inputs.configuration


def test_local_judge_fallback_preserves_explicit_cli_model(tmp_path):
    agents = [agent(tmp_path)]
    _, current = resume(agents, ENV, {**ENV, 'OPENROUTER_MODEL': 'unused'}, sdk='local', model='cli-judge')
    assert current['sdk_configuration']['judge']['model'] == 'cli-judge'


def test_replace_credential_rotation_and_abb_model_defaults(tmp_path):
    agents = [agent(tmp_path, 'langgraph')]
    resume(agents, ENV, {**ENV, 'OPENROUTER_API_KEY': 'rotated-router'})
    with pytest.raises(SuiteProvenanceError):
        resume(agents, ENV, {**ENV, 'ABB_MODEL': 'changed-global-default'})


def test_native_declared_global_model_uses_sdk_cli_environment(tmp_path):
    agents = [agent(tmp_path)]
    manifest = agents[0].path / 'agent.toml'
    manifest.write_text(manifest.read_text().replace('env_keys = ["GLM_MODEL"',
                                                  'env_keys = ["ABB_MODEL", "GLM_MODEL"'))
    _, current = resume(agents, ENV, {**ENV, 'ABB_MODEL': 'ignored'}, model='cli-native')
    assert current['agent_models'][agents[0].agent_id]['runtime_settings']['ABB_MODEL'] == 'cli-native'
