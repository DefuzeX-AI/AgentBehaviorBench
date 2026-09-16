"""Read the optional Agent declaration governing automatic whole-Case replay."""
try:
    import tomllib
except ModuleNotFoundError:  # pragma: no cover - Python 3.10 compatibility
    import tomli as tomllib


def safe_case_replay(registration):
    """Default to false; only an explicit boolean declaration enables replay."""
    path = registration.path / 'agent.toml'
    if not path.is_file():
        return False
    with path.open('rb') as stream:
        manifest = tomllib.load(stream)
    evaluation = manifest.get('evaluation', {})
    if not isinstance(evaluation, dict):
        raise ValueError('Manifest [evaluation] must be a table')
    value = evaluation.get('replay_safe', False)
    if type(value) is not bool:
        raise ValueError('evaluation.replay_safe must be a boolean')
    return value
