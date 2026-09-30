"""Public execution facts for SDKs; no evaluator formats or credentials."""
from dataclasses import asdict, dataclass, field


ENVIRONMENT_FILE = 'execution-environment.json'


@dataclass(frozen=True)
class ExecutionEnvironment:
    runtime: str = 'unknown'
    working_directory: str | None = None
    limits: dict = field(default_factory=dict)
    filesystem: dict = field(default_factory=dict)
    network: dict = field(default_factory=dict)
    process: dict = field(default_factory=dict)
    workspace: dict | None = None

    def as_dict(self):
        return {'schema': 'abb.execution_environment.v1', **asdict(self)}

    @classmethod
    def from_dict(cls, value):
        if value.get('schema') != 'abb.execution_environment.v1':
            raise ValueError('Unsupported execution environment schema')
        return cls(**{key: item for key, item in value.items() if key != 'schema'})
