"""Read confirmed defect declarations without invoking Agent runtime preflight."""

from pathlib import Path

from agentbench.harness.registry import tomllib

from .files import (GroundTruthError, label, read_bytes, read_json, records_field, text_field, within)

MANIFEST_SCHEMA = 'abb.agent.ground_truth.case.v1'


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
    """Read small GT descriptions; open saved traces only after summary matching."""
    unit = Path(unit).resolve()
    root = within(unit, unit / 'ground_truth')
    if not root.exists():
        return None
    paths = sorted(root.glob('*/gt.json'))
    if not paths:
        if any((root / name).exists() for name in ('manifest.json', 'ground_truth.json')):
            raise GroundTruthError('Legacy GT: migrate to complete case directories with gt.json')
        return None
    identity = tomllib.loads(read_bytes(within(unit, unit / 'agent.toml')).decode('utf-8'))
    if identity.get('agent_id') != agent_id:
        raise GroundTruthError('Agent identity differs from registry')
    seen, defects = set(), []
    for path in paths:
        path = within(root, path)
        defect = read_json(path)
        if defect.get('schema') != MANIFEST_SCHEMA or defect.get('agent_id') != agent_id:
            raise GroundTruthError('Invalid gt.json schema or Agent identity')
        identifier = text_field(defect, 'id')
        if identifier in seen:
            raise GroundTruthError('Duplicate GT identity')
        seen.add(identifier)
        for field in ('summary', 'explanation'):
            text_field(defect, field)
        case_directory = path.parent
        if not within(case_directory, case_directory / 'case.json').is_file():
            raise GroundTruthError('GT requires the original case.json')
        attempts = defect.get('reference_attempts')
        if (not isinstance(attempts, list) or not attempts or
                any(not isinstance(a, str) or not a or Path(a).name != a or a in ('.', '..')
                    or '/' in a or chr(92) in a for a in attempts)):
            raise GroundTruthError('reference_attempts must name retained attempt directories')
        if len(set(attempts)) != len(attempts):
            raise GroundTruthError('Duplicate reference attempt')
        for attempt in attempts:
            parent = 'trajectory' if (case_directory / 'trajectory').is_dir() else 'attempts'
            folder = within(case_directory, case_directory / parent / attempt)
            if not folder.is_dir():
                raise GroundTruthError('Reference attempt directory is unavailable')
        defects.append({**defect, '_case_directory': case_directory})
    return defects
