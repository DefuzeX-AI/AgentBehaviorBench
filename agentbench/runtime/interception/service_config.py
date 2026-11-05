"""Prepare per-run service data; framework behavior owns credential substitution."""
from dataclasses import asdict
import secrets
from .target_routing import resolve_target_routing


def prepare_service_config(interception, *, agent_id, max_trace_bytes, secret_dir,
                           secret_resolver, environ, model_provider=None, egress_proxy=None):
    """Return service JSON data and explicitly declared Agent credential env.

    Observe never resolves a model target, reads a replacement secret or creates
    fake credentials. Native credentials remain in the Agent's declared runtime.
    ``egress_proxy`` is the ``(host, port)`` of the egress observer that receives
    traffic matching neither a model nor a tool route; without it that traffic is
    denied by the interceptor.
    """
    data = {'agent_id': agent_id, 'max_trace_bytes': max_trace_bytes,
            'mode': interception.mode, 'credentials': [],
            'observation_headers': dict(interception.observation_headers),
            'observation_tool_purposes': dict(interception.observation_tool_purposes),
            'routes': [_route_data(r) for r in interception.routes],
            'tool_routes': [asdict(r) for r in interception.tool_routes],
            'token_counting': dict(interception.token_counting)}
    if egress_proxy is not None:
        data['egress_proxy'] = {'host': egress_proxy[0], 'port': egress_proxy[1]}
    token_environment = {}
    if interception.mode == 'observe':
        data['token_counting'] = {}
        return data, {c.agent_env: environ[c.agent_env] for c in interception.credentials
                      if environ.get(c.agent_env)}
    plan = resolve_target_routing(environ, model_provider)
    prepared_targets = {}
    for name, target in plan.targets.items():
        filename = f'target-{name}.secret' if plan.explicit else 'target.secret'
        (secret_dir / filename).write_text(secret_resolver.require(target.credential_env), encoding='utf-8')
        prepared = {'provider_id': target.provider_id, 'target_plugin': target.target_plugin,
                    'base_url': target.base_url, 'model': target.model, 'headers': dict(target.headers),
                    'secret_file': f'/run/secrets/{filename}', 'input_modalities': list(plan.inputs[name])}
        if getattr(target, 'endpoint_paths', None) is not None:
            prepared['endpoint_paths'] = dict(target.endpoint_paths)
        prepared_targets[name] = prepared
    if plan.explicit:
        data.update(targets=prepared_targets, target_rules=list(plan.rules))
    else:
        data['target'] = prepared_targets['default']
        # Preserve the legacy config contract: source credentials own its secret.
        data['target'].pop('secret_file')
    for credential in interception.credentials:
        token = secrets.token_urlsafe(32)
        token_file = secret_dir / f'{credential.credential_id}.token'
        token_file.write_text(token, encoding='utf-8')
        token_environment[credential.agent_env] = token
        item = {'id': credential.credential_id, 'auth_plugin': credential.auth_plugin,
                'token_file': f'/run/secrets/{token_file.name}'}
        if not plan.explicit:
            item['secret_file'] = '/run/secrets/target.secret'
        data['credentials'].append(item)
    return data, token_environment


def _route_data(route):
    data = asdict(route)
    data['id'] = data.pop('route_id')
    data['credential'] = data.pop('credential_id')
    return data
