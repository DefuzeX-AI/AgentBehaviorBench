"""Runtime paths and limits shared by SDK workers."""
from dataclasses import dataclass

STORAGE = '/run/abb-sdk-storage'


@dataclass(frozen=True)
class ResponseLimits:
    """Per-invocation copying budget, independent of SDK evidence retention."""
    max_bytes: int = 1024 * 1024 * 1024
    max_files: int = 20000

    def __post_init__(self):
        for name in ('max_bytes', 'max_files'):
            if type(getattr(self, name)) is not int or getattr(self, name) <= 0:
                raise ValueError(f'Agent response {name} must be a positive integer')

    @classmethod
    def from_environ(cls, environ):
        values = {}
        for field, key in (('max_bytes', 'ABB_AGENT_RESPONSE_MAX_BYTES'),
                           ('max_files', 'ABB_AGENT_RESPONSE_MAX_FILES')):
            if key not in environ:
                continue
            try:
                value = int(environ[key])
                if value <= 0:
                    raise ValueError()
            except (TypeError, ValueError):
                raise ValueError(f'{key} must be a positive integer') from None
            values[field] = value
        return cls(**values)
