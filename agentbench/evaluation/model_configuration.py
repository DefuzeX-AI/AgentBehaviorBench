"""Public model provenance for the selected Agent execution paths."""
from agentbench.harness.session.plan import public_configuration
from agentbench.observe.store import environment_secrets, is_secret_field
from agentbench.runtime.interception.config import InterceptionConfig, tomllib
from agentbench.runtime.interception.target_routing import resolve_target_routing


def agent_model_configuration(registrations, *, environ, model):
    """Resolve only targets these Agents use, including default ACP model selection.

    Native Agents receive their declared runtime settings plus manifest overrides.
    Secret declarations are authoritative even when their names look non-secret.
    Replacement routing uses the same resolver as the interceptor, including all
    configured targets and protocol rules. No credential values are retained.
    """
    # Container SDK runners forward the explicit CLI choice through ABB_MODEL.
    # Match that path for entry-point providers as well as catalog providers.
    environ = dict(environ)
    if model is not None:
        environ['ABB_MODEL'] = model
    result = {}
    for agent in registrations:
        manifest_path = agent.path / 'agent.toml'
        if not manifest_path.is_file():
            # Custom SDKs may own their execution without an ABB runtime manifest.
            result[agent.agent_id] = {'mode': 'sdk'}
            continue
        with manifest_path.open('rb') as stream:
            manifest = tomllib.load(stream)
        interception = InterceptionConfig.from_agent_dir(agent.path)
        mode = interception.mode if interception is not None else 'direct'
        if interception is not None and mode == 'replace':
            from agentbench.runtime.interception.native_model import select_model_provider
            resolved = resolve_target_routing(environ, select_model_provider(manifest, environ))
            secrets = (*environment_secrets(environ),
                       *(environ.get(target.credential_env, '') for target in resolved.targets.values()))
            routing = public_configuration({
                'targets': {name: {
                    'provider_id': target.provider_id, 'model': target.model,
                    'base_url': target.base_url, 'target_plugin': target.target_plugin,
                    'endpoint_paths': dict(target.endpoint_paths) if target.endpoint_paths is not None else None,
                    'headers': dict(target.headers),
                } for name, target in resolved.targets.items()},
                'inputs': resolved.inputs, 'rules': resolved.rules, 'explicit': resolved.explicit,
            }, secrets)
            result[agent.agent_id] = {'mode': mode, 'routing': routing}
            continue
        from agentbench.runtime.interception.native_model import resolve_shared_model, model_declaration
        shared = resolve_shared_model(manifest, environ)
        runtime = manifest.get('runtime', {})
        private = set(runtime.get('secret_env_keys', ())) | set(runtime.get('optional_secret_env_keys', ()))
        if interception is not None:
            private.update(item.agent_env for item in interception.credentials)
        names = (*runtime.get('env_keys', ()), *runtime.get('worker_env_keys', ()))
        settings = {name: environ[name] for name in names if name in environ}
        if interception is not None:
            settings.update(interception.environment)
        secrets = (*environment_secrets(environ), *(environ.get(name, '') for name in private))
        settings = {name: value for name, value in settings.items()
                    if name not in private and not is_secret_field(name)}
        result[agent.agent_id] = {'mode': mode,
                                  'runtime_settings': public_configuration(settings, secrets)}
        if manifest.get('model', {}).get('provider'):
            result[agent.agent_id]['provider_pin'] = manifest['model']['provider']
        if shared is not None:
            result[agent.agent_id]['model_source'] = model_declaration(manifest)[0]
            if manifest.get('model', {}).get('runtime_configurable'):
                result[agent.agent_id]['runtime_configurable'] = True
            result[agent.agent_id]['target'] = public_configuration({
                'provider_id': shared.provider_id, 'model': shared.model,
                'base_url': shared.base_url, 'target_plugin': shared.target_plugin,
            }, (*secrets, environ.get(shared.credential_env, '')))
    return result
