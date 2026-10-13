"""Provider-neutral handoff after execution resources have been released."""
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class DeferredJudgment:
    directory: Path
    dependency_failure: dict | None = None

    def __post_init__(self):
        object.__setattr__(self, 'directory', Path(self.directory).resolve())
