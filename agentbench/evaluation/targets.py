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
    if method == 'bundled' and manifest.get('source', {}).get('repository'):
        method = 'git'  # A bundled unit with a recorded repository can be fetched at the requested commit.
    if method not in ('git', 'install'):
        raise ValueError('Historical preparation supports git and install source methods')
    strategy = recipe.get('strategy')
    if method == 'install' and strategy not in ('source', 'release'):
        raise ValueError('Install Agent needs [historical] strategy="source" and a Dockerfile')
    if recipe and strategy not in ('source', 'release'):
        raise ValueError('Unsupported historical build strategy')
    release = strategy == 'release'
    if release:
        # The pinned release is the historical version only when its commit is the requested one.
        if method != 'install':
            raise ValueError('Historical release strategy requires an install Agent')
        # Further pinned releases may be listed as historical/releases/<commit>.json.
        release_file = root / 'historical' / 'releases' / (revision + '.json')
        if not release_file.is_file():
            release_file = root / 'install' / 'distribution.json'
        distribution = json.loads(release_file.read_text(encoding='utf-8'))
        if str(distribution.get('commit', '')).lower() != revision:
            raise ValueError('Requested commit is not a pinned release; a source recipe is required')
    else:
        text = _table(text, 'source', {'method': 'git', 'revision': revision})
    if recipe and (not release or 'dockerfile' in recipe):
        dockerfile = recipe.get('dockerfile')
        if not isinstance(dockerfile, str) or not dockerfile:
            raise ValueError('Historical source recipe needs a Dockerfile')
        path = root / dockerfile
        if not path.resolve().is_relative_to(root) or not path.is_file():
            raise ValueError('Historical Dockerfile must exist inside the Agent unit')
        text = _table(text, 'build', {'dockerfile': dockerfile})
    spec = source_spec(tomllib.loads(text))
    if recipe.get('omit_submodules') is True and not release:
        spec = replace(spec, omit_submodules=True)
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
                         or n.startswith('.abb-') or (method == 'install' and not release and n == 'install')]
        return excluded
    with tempfile.TemporaryDirectory(prefix='.prepare-', dir=parent) as temporary:
        staged = Path(temporary) / 'unit'
        shutil.copytree(root, staged, ignore=ignore, symlinks=True)
        if any(p.is_symlink() for p in staged.rglob('*')):
            raise ValueError('Prepared integration files must not contain symlinks')
        (staged / 'agent.toml').write_text(text, encoding='utf-8')
        if release:
            # The selected release becomes the unit's install input, so it also keys the fingerprint.
            shutil.copy2(release_file, staged / 'install' / 'distribution.json')
        fingerprint = hashlib.sha256(('abb.prepared-target.v1\n' + source_digest(staged)).encode()).hexdigest()
        target = parent / fingerprint[:24]
        with cache_lock(parent / (fingerprint + '.lock'), bounded):
            if not target.exists():
                archive = None if release else source_archive(spec, source_cache, bounded, output_fn)
                if archive is not None:
                    # In-tree file links are materialized later in the private build snapshot.
                    extract_source(archive, staged / 'agent', bounded, allow_symlinks=True)
                # Reuse installation overlays and runtime configuration checks.
                prepare_agent_source(staged, cache_dir=source_cache, check=bounded,
                                     output_fn=output_fn)
                provenance = {'schema': 'abb.prepared-target.v1', 'agent_id': registration.agent_id,
                              'requested_revision': revision,
                              'resolved_revision': revision if release else spec.revision,
                              'repository': manifest['source'].get('repository') if release else spec.repository,
                              'original_method': method,
                              'strategy': strategy or 'source', 'fingerprint': fingerprint,
                              'archive_sha256': None if archive is None
                              else hashlib.sha256(archive.read_bytes()).hexdigest()}
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
