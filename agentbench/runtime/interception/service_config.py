"""Prepare per-run service data; framework behavior owns credential substitution."""
from dataclasses import asdict
import secrets
from .providers import resolve_model_provider


def prepare_service_config(interception, *, agent_id, max_trace_bytes, secret_dir,
                           secret_resolver, environ, model_provider=None):
    """Return service JSON data and explicitly declared Agent credential env.

    Observe never resolves a model target, reads a replacement secret or creates
    fake credentials. Native credentials remain in the Agent's declared runtime.
    """
    data = {'agent_id': agent_id, 'max_trace_bytes': max_trace_bytes,
            'mode': interception.mode, 'credentials': [],
            'observation_headers': dict(interception.observation_headers),
            'routes': [_route_data(r) for r in interception.routes],
            'tool_routes': [asdict(r) for r in interception.tool_routes],
            'token_counting': dict(interception.token_counting)}
    token_environment = {}
    if interception.mode == 'observe':
        data['token_counting'] = {}
        return data, {c.agent_env: environ[c.agent_env] for c in interception.credentials
                      if environ.get(c.agent_env)}
    target = (model_provider or resolve_model_provider(environ=environ)).resolve(environ)
    upstream_secret = secret_resolver.require(target.credential_env)
    (secret_dir / 'target.secret').write_text(upstream_secret, encoding='utf-8')
    data['target'] = {'provider_id': target.provider_id, 'target_plugin': target.target_plugin,
                      'base_url': target.base_url, 'model': target.model, 'headers': dict(target.headers)}
    for credential in interception.credentials:
        token = secrets.token_urlsafe(32)
        token_file = secret_dir / f'{credential.credential_id}.token'
        token_file.write_text(token, encoding='utf-8')
        token_environment[credential.agent_env] = token
        data['credentials'].append({'id': credential.credential_id, 'auth_plugin': credential.auth_plugin,
                                    'token_file': f'/run/secrets/{token_file.name}',
                                    'secret_file': '/run/secrets/target.secret'})
    return data, token_environment


def _route_data(route):
    data = asdict(route)
    data['id'] = data.pop('route_id')
    data['credential'] = data.pop('credential_id')
    return data
