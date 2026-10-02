"""Read confirmed defect declarations without invoking Agent runtime preflight."""

from pathlib import Path

from agentbench.harness.registry import tomllib
from agentbench.harness.session.plan import digest_json

from .files import (GroundTruthError, file_digest, hash_field, label, read_bytes,
                    read_json, records_field, text_field, timestamp_field, within)

MANIFEST_SCHEMA = 'abb.agent.ground_truth.v1'


def registered_units(root):
    """Return safe registered paths and invalid identities; do not read Agent source."""
    root = Path(root).resolve()
    registry_path = root / 'resources' / 'registry.toml'
    if not registry_path.exists():
        return {}, set(), []
    try:
        registry = tomllib.loads(read_bytes(within(root, registry_path)).decode('utf-8'))
        entries = records_field(registry, 'agents')
    except (GroundTruthError, ValueError, UnicodeError):
        return {}, None, ['Ground truth: Agent registry is invalid or unavailable']
    units, invalid, warnings = {}, set(), []
    seen = set()
    for entry in entries:
        identifier = entry.get('agent_id')
        if not isinstance(identifier, str) or not identifier:
            warnings.append('Ground truth: registry contains an invalid Agent identity')
            continue
        try:
            if identifier in seen:
                raise GroundTruthError('duplicate Agent registration')
            seen.add(identifier)
            path = text_field(entry, 'path')
            unit = within(root, root / path)
            if unit == root:
                raise GroundTruthError('Agent unit must be below the project directory')
            units[identifier] = unit
        except GroundTruthError as error:
            units.pop(identifier, None)
            invalid.add(identifier)
            warnings.append(f'Ground truth Agent {label(identifier)}: {error}')
    return units, invalid, warnings


def load_manifest(unit, agent_id):
    """Validate all defects and retained observation hashes, or reject this manifest."""
    unit = Path(unit).resolve()
    directory = within(unit, unit / 'ground_truth')
    path = within(directory, directory / 'manifest.json')
    if not path.exists():
        return None
    try:
        identity = tomllib.loads(read_bytes(within(unit, unit / 'agent.toml')).decode('utf-8'))
    except (ValueError, UnicodeError) as error:
        raise GroundTruthError('Agent manifest is invalid') from error
    if identity.get('agent_id') != agent_id:
        raise GroundTruthError('registered Agent identity does not match agent.toml')
    document = read_json(path)
    if document.get('schema') != MANIFEST_SCHEMA:
        raise GroundTruthError('unsupported manifest schema')
    if document.get('agent_id') != agent_id:
        raise GroundTruthError('manifest Agent identity does not match its registration')
    defects, seen = [], set()
    for record in records_field(document, 'defects'):
        identifier = text_field(record, 'id')
        if identifier in seen:
            raise GroundTruthError('duplicate defect identity')
        seen.add(identifier)
        for key in ('title', 'expected_behavior', 'observed_behavior', 'confirmed_by'):
            text_field(record, key)
        timestamp_field(record, 'confirmed_at')
        hash_field(record, 'source_sha256')
        case_hash = hash_field(record, 'case_sha256')
        observations = records_field(record, 'observations')
        observation_ids, evidence_paths = set(), set()
        for observation in observations:
            observation_id = text_field(observation, 'id')
            if observation_id in observation_ids:
                raise GroundTruthError('observation identities must be distinct')
            observation_ids.add(observation_id)
            if hash_field(observation, 'case_sha256') != case_hash:
                raise GroundTruthError('observations must repeat the same retained Case')
            evidence_path = Path(text_field(observation, 'evidence_path'))
            if evidence_path.is_absolute() or '..' in evidence_path.parts:
                raise GroundTruthError('evidence_path must be relative to ground_truth')
            evidence = within(directory, directory / evidence_path)
            if evidence in evidence_paths:
                raise GroundTruthError('observations must retain distinct evidence files')
            evidence_paths.add(evidence)
            if file_digest(evidence) != hash_field(observation, 'evidence_sha256'):
                raise GroundTruthError('observation evidence digest does not match')
        if len(observation_ids) < 2:
            raise GroundTruthError('confirmed defects require at least two observations')
        defects.append({**record, 'ground_truth_sha256': digest_json(record)})
    return defects
