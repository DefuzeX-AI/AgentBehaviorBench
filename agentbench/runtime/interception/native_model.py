"""Apply default model selection and explicit per-Agent provider pins."""
from dataclasses import replace
import re
from urllib.parse import urlsplit

from .config import InterceptionConfigurationError, RouteConfig, ToolRouteConfig
from .providers import resolve_model_provider, DeferredModelTargetProvider
from .target_routing import _validate_target

KEY_ENV = 'ABB_AGENT_MODEL_API_KEY'
BASE_ENV = 'ABB_AGENT_MODEL_BASE_URL'
MODEL_ENV = 'ABB_AGENT_MODEL'
PROVIDER_ENV = 'ABB_AGENT_MODEL_PROVIDER'
ENV_KEYS = (KEY_ENV, BASE_ENV, MODEL_ENV, PROVIDER_ENV)


def model_declaration(manifest):
    """No provider inherits run defaults; native integrations declare a fixed provider."""
    declaration = manifest.get('model', {})
    if not isinstance(declaration, dict) or set(declaration) - {'provider', 'source', 'reason', 'metadata_paths', 'runtime_configurable'}:
        raise InterceptionConfigurationError('model accepts provider, source, reason, metadata_paths and runtime_configurable')
    provider = declaration.get('provider')
    if 'provider' in declaration and (not isinstance(provider, str)
            or not re.fullmatch(r'[a-z][a-z0-9_-]*', provider)):
        raise InterceptionConfigurationError('model.provider must be a lowercase provider name')
    if 'source' in declaration and declaration['source'] != 'native':
        raise InterceptionConfigurationError('Omit model.source for default selection; only native integrations need source="native"')
    observed = manifest.get('framework') == 'acp'
    source = 'shared' if observed else 'replace'
    if 'llm_interception' not in manifest:
        source = 'direct'
    if declaration.get('source') == 'native':
        if not observed or not provider:
            raise InterceptionConfigurationError('Native model integration requires ACP and an explicit model.provider')
        source = 'native'
    elif provider and source == 'direct':
        raise InterceptionConfigurationError('A model.provider pin requires a model integration')
    if 'reason' in declaration and (not isinstance(declaration['reason'], str) or not declaration['reason'].strip()):
        raise InterceptionConfigurationError('model.reason must be non-empty text')
    configurable = declaration.get('runtime_configurable', False)
    if 'runtime_configurable' in declaration:
        if type(configurable) is not bool:
            raise InterceptionConfigurationError('model.runtime_configurable must be a boolean')
        if source != 'native' or not declaration.get('reason') or 'llm_interception' not in manifest:
            raise InterceptionConfigurationError('model.runtime_configurable requires native ACP, an explicit provider and reason, and interception')
    paths = declaration.get('metadata_paths', [])
    if not isinstance(paths, list) or any(path != '/models' for path in paths) or len(paths) > 1:
        raise InterceptionConfigurationError('model.metadata_paths supports only ["/models"]')
    if source == 'shared' or configurable:
        section = manifest['llm_interception']
        if not isinstance(section, dict):
            raise InterceptionConfigurationError('llm_interception must be a table')
        if section.get('routes') or section.get('credentials') or section.get('environment'):
            raise InterceptionConfigurationError('Runtime-configurable ACP model routes and credentials are resolved at runtime; remove static overrides or declare a fixed native integration')
        runtime = manifest.get('runtime', {})
        declared = {key for field in ('env_keys', 'secret_env_keys', 'optional_secret_env_keys', 'worker_env_keys')
                    for key in runtime.get(field, [])}
        if declared.intersection(ENV_KEYS):
            raise InterceptionConfigurationError('ABB_AGENT_MODEL variables are runtime-owned; do not declare them as inputs')
    elif paths:
        raise InterceptionConfigurationError('model.metadata_paths requires shared model selection')
    return source, tuple(paths)


def uses_runtime_model(manifest):
    """Keep native provenance while opting a compatible client into runtime selection."""
    source, _ = model_declaration(manifest)
    return source == 'shared' or manifest.get('model', {}).get('runtime_configurable', False)


def select_model_provider(manifest, environ, fallback=None):
    """Per-Agent pins win over run-level provider choices, without changing shared state."""
    source, _ = model_declaration(manifest)
    provider = manifest.get('model', {}).get('provider')
    if source == 'direct' or (source == 'native' and not uses_runtime_model(manifest)) or not provider:
        return fallback
    if environ.get('ABB_MODEL_ROUTING_CONFIG', '').strip():
        raise InterceptionConfigurationError('A fixed model.provider cannot be combined with multi-target routing')
    model = fallback.model if isinstance(fallback, DeferredModelTargetProvider) else None
    return resolve_model_provider(provider, model=model, environ=environ)


def resolve_shared_model(manifest, environ, model_provider=None):
    if not uses_runtime_model(manifest):
        return None
    if environ.get('ABB_MODEL_ROUTING_CONFIG', '').strip():
        raise InterceptionConfigurationError('Shared native Agents use one model; multi-target routing is only supported in replacement mode')
    target = (select_model_provider(manifest, environ, model_provider) or resolve_model_provider(environ=environ)).resolve(environ)
    _validate_target(target)
    if target.target_plugin not in ('openrouter', 'compatible-json'):
        raise InterceptionConfigurationError('Shared native Agents require an OpenAI Chat Completions compatible provider')
    if target.headers:
        raise InterceptionConfigurationError('Shared native launchers do not support custom provider headers; remove header overrides')
    endpoint = (target.endpoint_paths or {}).get('/chat/completions', '/chat/completions')
    if target.endpoint_paths is not None and '/chat/completions' not in target.endpoint_paths:
        raise InterceptionConfigurationError('Selected provider does not declare a Chat Completions endpoint')
    if not endpoint.endswith('/chat/completions'):
        raise InterceptionConfigurationError('Shared native launchers require an endpoint ending in /chat/completions')
    # Native OpenAI clients append /chat/completions. Preserve the catalog prefix.
    base = target.base_url.rstrip('/') + endpoint[:-len('/chat/completions')]
    parsed = urlsplit(base)
    if any(c in (parsed.hostname + parsed.path) for c in '*?[]') or any(c.isspace() for c in base):
        raise InterceptionConfigurationError('Shared model URL must name an exact host and path without wildcards')
    return replace(target, base_url=base, endpoint_paths=None)


def model_environment(target, secret_resolver):
    return {KEY_ENV: secret_resolver.require(target.credential_env),
            BASE_ENV: target.base_url, MODEL_ENV: target.model, PROVIDER_ENV: target.provider_id}


def bind_model_routes(interception, target, metadata_paths=()):
    if target is None:
        return interception
    if interception is None or interception.mode != 'observe':
        raise InterceptionConfigurationError('Shared native models must remain in observe mode')
    parsed = urlsplit(target.base_url)
    route = RouteConfig('shared-openai-chat', (parsed.hostname,), (parsed.port or 443,),
                        ('POST',), (parsed.path.rstrip('/') + '/chat/completions',), 'openai-chat', '')
    metadata = tuple(ToolRouteConfig((parsed.hostname,), (parsed.port or 443,), ('GET',),
                                    (parsed.path.rstrip('/') + path,), 'metadata') for path in metadata_paths)
    return replace(interception, routes=(route,), tool_routes=interception.tool_routes + metadata)
