"""Freeze external repair source as a new target without restoring deleted files."""
from dataclasses import replace
import hashlib
import json
import os
from pathlib import Path
import shutil

from agentbench.harness.session.plan import source_digest
from agentbench.runtime.docker.worker_build import agent_build_ignore, source_build_ignore
from agentbench.runtime.source.preparation import prepare_installation_inputs
from .targets import PreparedTarget, _table


def copy_source(source, destination):
    """Copy the same source selection used by worker builds, rejecting links."""
    source = Path(source).resolve(strict=True)
    if not source.is_dir():
        raise ValueError('Source must be a directory')
    before = source_digest(source)
    # Inspect links before copying; Windows junctions are not always symlinks.
    for directory, folders, files in os.walk(source, followlinks=False):
        excluded = set(source_build_ignore(directory, folders + files))
        folders[:] = [name for name in folders if name not in excluded]
        for name in folders + [name for name in files if name not in excluded]:
            path = Path(directory) / name
            if path.is_symlink() or not path.resolve().is_relative_to(source):
                raise ValueError('External source contains a link: ' + str(path))
    shutil.copytree(source, destination, ignore=source_build_ignore, symlinks=True)
    if any(path.is_symlink() for path in Path(destination).rglob('*')):
        raise ValueError('External source changed to contain a link while copying')
    if source_digest(source) != before:
        raise ValueError('External source changed while copying; retry with stable source')


def prepare_modified_target(base, source, destination):
    """Keep the baseline immutable; use a whole replacement source tree per run."""
    base.validate()
    source = Path(source).resolve(strict=True)
    destination = Path(destination).resolve()
    if destination.exists():
        raise ValueError('Modified target destination already exists')
    if destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError('Modified target and source must not overlap')
    root = base.registration.path
    if destination.is_relative_to(root.resolve()) or root.resolve().is_relative_to(destination):
        raise ValueError('Modified target must not overlap the historical baseline')
    ignore_base = agent_build_ignore(root)
    def ignore(directory, names):
        ignored = ignore_base(directory, names)
        if Path(directory).resolve() == root.resolve():
            ignored += [name for name in names if name in {'agent', 'provenance.json'}]
        return ignored
    shutil.copytree(root, destination, ignore=ignore, symlinks=True)
    if any(path.is_symlink() for path in destination.rglob('*')):
        raise ValueError('Target integration contains a link')
    copy_source(source, destination / 'agent')
    submitted_digest = source_digest(destination / 'agent')
    # Bundled applies the existing installation overlays but never downloads or
    # restores missing upstream source. Conflicting overlays fail explicitly.
    manifest = destination / 'agent.toml'
    manifest.write_text(_table(manifest.read_text(encoding='utf-8'), 'source',
                              {'method': 'bundled'}), encoding='utf-8')
    prepare_installation_inputs(destination)
    provenance = {'schema': 'abb.modified-target.v1', 'agent_id': base.registration.agent_id,
                  'base_revision': base.revision, 'base_target': base.describe(),
                  'submitted_source_sha256': submitted_digest,
                  'effective_source_sha256': source_digest(destination / 'agent'),
                  'source_is_modified': source_digest(destination / 'agent') != source_digest(root / 'agent')}
    (destination / 'provenance.json').write_text(
        json.dumps(provenance, ensure_ascii=False, indent=2), encoding='utf-8')
    digest = source_digest(destination)
    fingerprint = hashlib.sha256(('abb.modified-target.v1\n' + digest).encode()).hexdigest()
    target = PreparedTarget(replace(base.registration, path=destination,
        requirement_path=destination / 'requirement.md'), base.revision, fingerprint, digest)
    target.validate()
    return target
