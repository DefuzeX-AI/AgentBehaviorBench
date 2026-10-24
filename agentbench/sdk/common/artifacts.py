"""Full, redacted snapshots, including immutable SDK public contracts."""
from collections.abc import Mapping
from dataclasses import fields, is_dataclass
from agentbench.observe.store import atomic_json, environment_secrets, redact


def plain(value):
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: plain(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, Mapping):
        return {str(key): plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [plain(item) for item in value]
    return value


class Artifacts:
    def __init__(self, directory, *, environ=None):
        self.directory = directory
        self.secrets = environment_secrets(environ)

    def save(self, relative, value):
        path = self.directory / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        atomic_json(path, redact(plain(value), self.secrets))
