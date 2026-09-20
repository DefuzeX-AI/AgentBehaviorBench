"""Static ACP configuration; never starts a process or resolves credentials."""
from dataclasses import dataclass
from pathlib import Path
import math
try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


@dataclass(frozen=True)
class ACPConfig:
    root: Path
    command: tuple[str, ...]
    cwd: str
    env_keys: tuple[str, ...] = ()
    input_key: str | None = None
    permission_policy: str = 'deny'
    timeout: float = 2400
    handshake_timeout: float = 30
    cleanup_timeout: float = 3
    max_output_bytes: int = 8 * 1024 * 1024
    auth_method: str | None = None
    evidence_reader: str | None = None

    @classmethod
    def from_agent_dir(cls, root):
        root = Path(root).resolve()
        manifest = tomllib.loads((root / 'agent.toml').read_text())
        adapter = manifest.get('adapter', {})
        allowed = {'type', 'transport', 'command', 'cwd', 'env_keys', 'input_key',
                   'permission_policy', 'handshake_timeout', 'cleanup_timeout',
                   'max_output_bytes', 'auth_method', 'evidence_reader'}
        if not isinstance(adapter, dict) or adapter.get('type') != 'acp':
            raise ValueError('ACP requires adapter.type="acp"')
        if set(adapter) - allowed:
            raise ValueError('Unknown ACP adapter fields: ' + ', '.join(sorted(set(adapter) - allowed)))
        if adapter.get('transport', 'stdio') != 'stdio':
            raise ValueError('Only ACP stdio transport is supported')
        command = _strings(adapter.get('command'), 'command')
        if not command:
            raise ValueError('ACP command must be a non-empty argument array')
        cwd = adapter.get('cwd')
        if not isinstance(cwd, str) or not Path(cwd).is_absolute():
            raise ValueError('ACP cwd must be an absolute container path')
        policy = adapter.get('permission_policy', 'deny')
        if policy not in ('deny', 'allow_once'):
            raise ValueError('ACP permission_policy must be deny or allow_once')
        for key in ('input_key', 'auth_method'):
            if key in adapter and (not isinstance(adapter[key], str) or not adapter[key].strip()):
                raise ValueError(f'ACP {key} must be a non-empty string')
        from .evidence import validate_reader
        validate_reader(adapter.get('evidence_reader'))
        maximum = adapter.get('max_output_bytes', 8 * 1024 * 1024)
        if type(maximum) is not int or not 1024 <= maximum <= 32 * 1024 * 1024:
            raise ValueError('ACP max_output_bytes must be between 1024 and 33554432')
        runtime = manifest.get('runtime', {})
        keys = (*_strings(adapter.get('env_keys', []), 'env_keys'),
                *_strings(runtime.get('env_keys', []), 'runtime.env_keys'),
                *_strings(runtime.get('secret_env_keys', []), 'runtime.secret_env_keys'))
        # Observe mode forwards declared native credentials to the ACP process.
        interception = manifest.get('llm_interception', {})
        keys += tuple(item['agent_env'] for item in interception.get('credentials', [])
                      if isinstance(item, dict) and isinstance(item.get('agent_env'), str))
        return cls(root, tuple(command), cwd, tuple(dict.fromkeys(keys)),
                   adapter.get('input_key'), policy,
                   _seconds(runtime.get('timeout_sec', 2400), 'runtime.timeout_sec'),
                   _seconds(adapter.get('handshake_timeout', 30), 'handshake_timeout'),
                   _seconds(adapter.get('cleanup_timeout', 3), 'cleanup_timeout'),
                   maximum, adapter.get('auth_method'), adapter.get('evidence_reader'))

    def text_input(self, value):
        if self.input_key is not None:
            if not isinstance(value, dict) or self.input_key not in value:
                raise ValueError(f'ACP input must contain configured field {self.input_key!r}')
            value = value[self.input_key]
        if not isinstance(value, str):
            raise ValueError('ACP input must be text; configure input_key for structured input')
        return value


def _strings(value, name):
    if not isinstance(value, list) or any(not isinstance(x, str) or not x.strip() or '\0' in x for x in value):
        raise ValueError(f'ACP {name} must be an array of non-empty strings')
    return value


def _seconds(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0:
        raise ValueError(f'ACP {name} must be finite and positive')
    return float(value)
