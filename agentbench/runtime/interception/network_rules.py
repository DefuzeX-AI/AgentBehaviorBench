"""Load declarative Agent-owned network extensions without importing Agent code."""
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib


def load_network_rules(root: Path, reference: object) -> dict:
    """Read a relative, contained TOML file; return data for service validation.

    The extension has no Python execution, credential values or independent
    transport. Its routes still pass the normal host and service validation.
    """
    if reference is None:
        return {}
    if not isinstance(reference, str) or not reference.strip():
        raise ValueError('network_config must be a non-empty relative filename')
    path = Path(reference)
    resolved = (root / path).resolve()
    if path.is_absolute() or '..' in path.parts or not resolved.is_relative_to(root.resolve()):
        raise ValueError('network_config must stay inside the Agent unit')
    with resolved.open('rb') as stream:
        rules = tomllib.load(stream)
    if rules.get('schema_version') != 'abb.network.v1':
        raise ValueError('network_config requires schema_version abb.network.v1')
    if set(rules) - {'schema_version', 'tool_routes', 'token_counting'}:
        raise ValueError('Unknown network_config fields')
    if not isinstance(rules.get('token_counting', {}), dict):
        raise ValueError('token_counting must be a table')
    return rules


def stage_network_rules(source: Path, destination: Path, reference: object) -> None:
    """Stage a validated referenced file for isolated manifest validation."""
    if reference is None:
        return
    load_network_rules(source, reference)
    target = destination / reference
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes((source / reference).read_bytes())
