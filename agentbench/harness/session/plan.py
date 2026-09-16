"""Immutable Suite selection and non-secret execution provenance."""

from collections.abc import Mapping
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re

from agentbench.harness.registry import AgentRegistration
from agentbench.observe.store import redact

from .codec import json_value

PLAN_SCHEMA = 'abb.suite.plan.v1'
IGNORED_DIRECTORIES = {'.git', '.venv', 'venv', '__pycache__', '.pytest_cache',
                       '.mypy_cache', 'node_modules', '.cache', '.kuma', 'results', 'cache'}


class SuiteProvenanceError(ValueError):
    """A resume would combine results produced under different configurations."""


def validate_suite_id(suite_id):
    if not isinstance(suite_id, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', suite_id):
        raise ValueError('Suite ID must contain only letters, digits, underscores and hyphens')
    return suite_id


def environment_secrets(environ=None):
    values = os.environ if environ is None else environ
    return tuple(value for key, value in values.items() if isinstance(value, str) and value
                 and any(word in key.upper() for word in ('KEY', 'TOKEN', 'SECRET', 'PASSWORD')))


def public_configuration(value, secrets=()):
    """Omit credential/environment fields; redact known secrets in other values."""
    value = json_value(value)
    if isinstance(value, Mapping):
        clean = {}
        for key, item in value.items():
            words = set(re.split(r'[^a-z0-9]+', key.lower()))
            if (words & {'key', 'token', 'secret', 'password', 'authorization',
                         'environ', 'environment', 'credentials'}
                    or any(part in key.lower() for part in ('api_key', 'apikey', 'access_token'))):
                continue
            clean[key] = public_configuration(item, secrets)
        return clean
    if isinstance(value, list):
        return [public_configuration(item, secrets) for item in value]
    return redact(value, secrets)


def digest_json(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                     ensure_ascii=False, allow_nan=False).encode()).hexdigest()


def source_digest(root):
    """Hash Agent source, bindings, manifests and dependencies, excluding runtime caches."""
    root = Path(root).resolve(strict=True)
    digest = hashlib.sha256()
    for directory, folders, files in os.walk(root, followlinks=False):
        folders[:] = sorted(name for name in folders
                            if name not in IGNORED_DIRECTORIES and not name.endswith('.egg-info'))
        for name in sorted(files):
            if name == '.DS_Store' or name.startswith('.env') or name.endswith(('.pyc', '.pyo')):
                continue
            path = Path(directory) / name
            if not path.resolve().is_relative_to(root):
                raise SuiteProvenanceError('Agent source contains a link outside its registered directory')
            relative = path.relative_to(root).as_posix().encode()
            digest.update(len(relative).to_bytes(8, 'big'))
            digest.update(relative)
            digest.update(path.stat().st_size.to_bytes(8, 'big'))
            with path.open('rb') as stream:
                while block := stream.read(1024 * 1024):
                    digest.update(block)
    return digest.hexdigest()


def registration_record(agent):
    value = json_value(agent)
    value['path'] = str(agent.path.resolve())
    value['requirement_path'] = None if agent.requirement_path is None else str(agent.requirement_path.resolve())
    value['source_sha256'] = source_digest(agent.path)
    value['requirement_sha256'] = (None if agent.requirement_path is None else
                                    hashlib.sha256(agent.requirement_path.read_bytes()).hexdigest())
    return value


def build_plan(suite_id, registrations, *, configuration=None, secrets=(), result_log_path=None,
               origin_suite_id=None):
    agents = redact([registration_record(agent) for agent in registrations], secrets)
    if not agents or len({agent['agent_id'] for agent in agents}) != len(agents):
        raise ValueError('Suite plan requires distinct selected Agents')
    if any(type(agent['case_count']) is not int or agent['case_count'] < 1 for agent in agents):
        raise ValueError('Suite Case counts must be positive integers')
    config = public_configuration(configuration or {}, secrets)
    provenance = {'agents': agents, 'configuration': config}
    return {'schema': PLAN_SCHEMA, 'suite_id': validate_suite_id(suite_id),
            **({} if origin_suite_id is None else {'origin_suite_id': validate_suite_id(origin_suite_id)}),
            'created_at': datetime.now(timezone.utc).isoformat(), **provenance,
            'provenance_sha256': digest_json(provenance),
            'result_log_path': None if result_log_path is None else str(Path(result_log_path).resolve())}


def validate_plan(plan):
    if plan.get('schema') != PLAN_SCHEMA:
        raise ValueError('Unsupported Suite plan schema')
    validate_suite_id(plan.get('suite_id'))
    actual = digest_json({key: plan[key] for key in ('agents', 'configuration')})
    if actual != plan.get('provenance_sha256'):
        raise SuiteProvenanceError('Saved Suite plan provenance does not match its contents')
    return plan


def registrations_from_plan(plan):
    return tuple(AgentRegistration(value['agent_id'], Path(value['path']), value['enabled'],
                                   value['status'], value['framework'], value['source'],
                                   value['case_count'], None if value.get('requirement_path') is None
                                   else Path(value['requirement_path'])) for value in plan['agents'])


def validate_provenance(plan, registrations, configuration, *, secrets=()):
    current = build_plan(plan['suite_id'], registrations, configuration=configuration, secrets=secrets)
    if current['provenance_sha256'] != plan['provenance_sha256']:
        raise SuiteProvenanceError('Agent source or execution configuration changed; start a linked new Suite '
                                   'with the saved Cases instead of merging different evaluations')
