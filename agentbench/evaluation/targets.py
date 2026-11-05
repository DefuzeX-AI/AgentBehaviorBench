"""Prepare isolated, commit-addressed Agent units for existing executors."""
from dataclasses import dataclass, replace
import hashlib
import json
from pathlib import Path
import re
import shutil
import tempfile
import time

from agentbench.harness.registry import AgentRegistration, tomllib
from agentbench.harness.session.plan import source_digest
from agentbench.runtime.docker.worker_build import agent_build_ignore
from agentbench.runtime.source.cache import cache_lock, source_archive
from agentbench.runtime.source.config import source_spec
from agentbench.runtime.source.inventory import extract_source
from agentbench.runtime.source.preparation import prepare_agent_source


@dataclass(frozen=True)
class PreparedTarget:
    registration: AgentRegistration
    revision: str
    fingerprint: str
    digest: str

    def validate(self):
        if source_digest(self.registration.path) != self.digest:
            raise ValueError('Prepared Agent was modified; prepare a new target')

    def describe(self):
        return {'agent_id': self.registration.agent_id, 'revision': self.revision,
                'fingerprint': self.fingerprint, 'path': str(self.registration.path),
                'source_digest': self.digest}


def _table(source, name, values):
    """Change a flat manifest table, validating all other TOML values stay intact."""
    expected = tomllib.loads(source)
    expected[name] = {**expected.get(name, {}), **values}
    if any(isinstance(v, dict) for v in expected[name].values()):
        raise ValueError(f'Historical preparation requires a flat [{name}] table')
    body = '[' + name + ']\n' + ''.join(
        json.dumps(k) + ' = ' + json.dumps(v, ensure_ascii=False) + '\n'
        for k, v in expected[name].items())
    pattern = rf'(?ms)^\[{re.escape(name)}\][^\n]*\n.*?(?=^\[|\Z)'
    result, count = re.subn(pattern, lambda _: body + '\n', source)
    if count == 0:
        result = source + '\n' + body
    if tomllib.loads(result) != expected:
        raise ValueError(f'Cannot safely update [{name}] in Agent manifest')
    return result


def prepare_target(registration, revision, *, cache_dir, check=lambda: None,
                   output_fn=lambda text: None, timeout=300):
    """Acquire an exact Git commit; install units declare a source-build recipe.

    Does not build containers or invoke models. The existing runtime builds the
    prepared unit's Dockerfile. The default unit and registry are never changed.
    """
    if not isinstance(revision, str) or not re.fullmatch('[0-9a-fA-F]{40}', revision):
        raise ValueError('Target revision must be a full 40-character commit SHA')
    revision = revision.lower()
    root = registration.path.resolve()
    text = (root / 'agent.toml').read_text(encoding='utf-8')
    manifest = tomllib.loads(text)
    method = manifest.get('source', {}).get('method', 'bundled')
    recipe = manifest.get('historical', {})
    if not isinstance(recipe, dict):
        raise ValueError('historical must be a table')
    if method not in ('git', 'install'):
        raise ValueError('Historical preparation supports git and install source methods')
    if method == 'install' and recipe.get('strategy') != 'source':
        raise ValueError('Install Agent needs [historical] strategy="source" and a Dockerfile')
    if recipe and recipe.get('strategy') != 'source':
        raise ValueError('Unsupported historical build strategy')
    text = _table(text, 'source', {'method': 'git', 'revision': revision})
    if recipe:
        dockerfile = recipe.get('dockerfile')
        if not isinstance(dockerfile, str) or not dockerfile:
            raise ValueError('Historical source recipe needs a Dockerfile')
        path = root / dockerfile
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Historical Dockerfile must exist inside the Agent unit')
        text = _table(text, 'build', {'dockerfile': dockerfile})
    spec = source_spec(tomllib.loads(text))
    parent = Path(cache_dir).resolve()
    parent.mkdir(parents=True, exist_ok=True)
    source_cache = parent.parent / 'sources'
    end = time.monotonic() + timeout
    def bounded():
        check()
        if time.monotonic() >= end:
            raise TimeoutError('Historical Agent preparation timed out')
    ignore_base = agent_build_ignore(root)
    def ignore(directory, names):
        excluded = ignore_base(directory, names)
        if Path(directory).resolve() == root:
            excluded += [n for n in names if n in {'agent', 'source-manifest.json', 'provenance.json'}
                         or n.startswith('.abb-') or (method == 'install' and n == 'install')]
        return excluded
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=parent) as temporary:
        staged = Path(temporary) / 'unit'
        shutil.copytree(root, staged, ignore=ignore, symlinks=True)
        if any(p.is_symlink() for p in staged.rglob('*')):
            raise ValueError('Prepared integration files must not contain symlinks')
        (staged / 'agent.toml').write_text(text, encoding='utf-8')
        fingerprint = hashlib.sha256(('abb.prepared-target.v1\n' + source_digest(staged)).encode()).hexdigest()
        target = parent / fingerprint[:24]
        with cache_lock(parent / (fingerprint + '.lock'), bounded):
            if not target.exists():
                archive = source_archive(spec, source_cache, bounded, output_fn)
                extract_source(archive, staged / 'agent', bounded)
                # Reuse installation overlays and runtime configuration checks.
                prepare_agent_source(staged, cache_dir=source_cache, check=bounded,
                                     output_fn=output_fn)
                provenance = {'schema': 'abb.prepared-target.v1', 'agent_id': registration.agent_id,
                              'requested_revision': revision, 'resolved_revision': spec.revision,
                              'repository': spec.repository, 'original_method': method,
                              'strategy': 'source', 'fingerprint': fingerprint,
                              'archive_sha256': hashlib.sha256(archive.read_bytes()).hexdigest()}
                (staged / 'provenance.json').write_text(json.dumps(provenance, indent=2), encoding='utf-8')
                digest = source_digest(staged)
                # The marker stays outside the unit and is published under the same lock.
                (parent / (fingerprint + '.json')).write_text(json.dumps({'digest': digest}), encoding='utf-8')
                staged.rename(target)
            digest = json.loads((parent / (fingerprint + '.json')).read_text(encoding='utf-8'))['digest']
            prepared = PreparedTarget(replace(registration, path=target,
                requirement_path=target / 'requirement.md'), revision, fingerprint, digest)
            prepared.validate()
            return prepared
