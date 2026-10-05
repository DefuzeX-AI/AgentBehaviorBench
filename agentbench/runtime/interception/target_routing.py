"""Resolve run-level model targets and rules independently of Agent manifests."""
from dataclasses import dataclass, replace
from collections.abc import Mapping
from pathlib import Path
import re
from urllib.parse import urlsplit

from .config import InterceptionConfigurationError, tomllib
from .providers import ModelTargetConfig, resolve_model_provider

ROUTING_ENV = 'ABB_MODEL_ROUTING_CONFIG'


@dataclass(frozen=True)
class ModelRoutingPlan:
    targets: dict[str, ModelTargetConfig]
    inputs: dict[str, tuple[str, ...]]
    rules: tuple[dict, ...]
    explicit: bool = False


def resolve_target_routing(environ, model_provider=None):
    path = environ.get(ROUTING_ENV, '').strip()
    if not path:
        target = (model_provider or resolve_model_provider(environ=environ)).resolve(environ)
        # Preserve image-bearing generation requests for the selected run model.
        # The destination validates its real capabilities; do not select a new
        # model or require a routing file merely to pass images through.
        return ModelRoutingPlan({'default': target}, {'default': ('text', 'image')}, ())
    try:
        with Path(path).open('rb') as stream:
            raw = tomllib.load(stream)
    except (OSError, ValueError) as exc:
        raise InterceptionConfigurationError(f'Cannot read {ROUTING_ENV}') from exc
    if set(raw) - {'targets', 'rules'} or not isinstance(raw.get('targets'), dict) or not raw['targets']:
        raise InterceptionConfigurationError('Model routing requires a non-empty targets table and rules array')
    targets, inputs = {}, {}
    for name, data in raw['targets'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_-]{0,63}', name) or not isinstance(data, dict):
            raise InterceptionConfigurationError('Invalid model target name or definition')
        allowed = {'provider', 'model', 'use_run_target', 'base_url', 'credential_env',
                   'endpoint_paths', 'input_modalities'}
        if set(data) - allowed:
            raise InterceptionConfigurationError(f'Unknown settings for model target {name}')
        if 'use_run_target' in data and not isinstance(data['use_run_target'], bool):
            raise InterceptionConfigurationError('use_run_target must be boolean')
        if data.get('use_run_target'):
            if set(data) - {'use_run_target', 'input_modalities'}:
                raise InterceptionConfigurationError('use_run_target cannot be combined with provider overrides')
            target = (model_provider or resolve_model_provider(environ=environ)).resolve(environ)
        else:
            for field in ('provider', 'model'):
                _string(data.get(field), field)
            target = resolve_model_provider(data['provider'], model=data['model'], environ=environ).resolve(environ)
            overrides = {key: data[key] for key in ('base_url', 'credential_env', 'endpoint_paths') if key in data}
            target = replace(target, **overrides)
        _validate_target(target)
        modalities = _strings(data.get('input_modalities', ['text']), 'input_modalities')
        if 'text' not in modalities:
            raise InterceptionConfigurationError('Targets must support text input; image is an additional capability')
        targets[name], inputs[name] = target, modalities
    rules = validate_rules(raw.get('rules'), targets, inputs)
    return ModelRoutingPlan(targets, inputs, rules, explicit=True)


def validate_rules(raw, targets, inputs):
    if not isinstance(raw, list) or not raw:
        raise InterceptionConfigurationError('Model routing rules must be a non-empty array')
    seen, ids, result = set(), set(), []
    for rule in raw:
        if not isinstance(rule, dict) or set(rule) != {'id', 'target', 'protocols', 'input'}:
            raise InterceptionConfigurationError('Each model rule needs id, target, protocols and input')
        name, target, kind = (_string(rule[k], k) for k in ('id', 'target', 'input'))
        protocols = _strings(rule['protocols'], 'protocols')
        if name in ids or target not in targets:
            raise InterceptionConfigurationError('Duplicate model rule id or unknown target')
        if kind not in inputs[target]:
            raise InterceptionConfigurationError(f'Model target {target} does not declare {kind} input')
        for protocol in protocols:
            signature = (protocol, kind)
            if signature in seen:
                raise InterceptionConfigurationError(f'Ambiguous model target rules for {protocol}/{kind}')
            seen.add(signature)
        ids.add(name)
        result.append(dict(id=name, target=target, protocols=list(protocols), input=kind))
    return tuple(result)


def _validate_target(target):
    _string(target.credential_env, 'credential_env')
    try:
        parsed = urlsplit(_string(target.base_url, 'base_url'))
        port = parsed.port
    except ValueError as exc:
        raise InterceptionConfigurationError('Invalid target base_url') from exc
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or port == 0):
        raise InterceptionConfigurationError('Target base_url must be HTTPS without credentials, query or fragment')
    endpoints = target.endpoint_paths
    if endpoints is not None and (not isinstance(endpoints, Mapping)
            or not endpoints or any(not isinstance(k, str) or not k.startswith('/')
                or not isinstance(v, str) or not v.startswith('/') or v.startswith('//')
                or '?' in v or '#' in v or '..' in v.split('/') for k, v in endpoints.items())):
        raise InterceptionConfigurationError('Invalid target endpoint_paths')


def _string(value, field):
    if not isinstance(value, str) or not value.strip():
        raise InterceptionConfigurationError(f'{field} must be a non-empty string')
    return value.strip()


def _strings(value, field):
    if not isinstance(value, list) or not value:
        raise InterceptionConfigurationError(f'{field} must be a non-empty string list')
    return tuple(_string(item, field) for item in value)
