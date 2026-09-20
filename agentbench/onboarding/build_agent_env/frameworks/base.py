"""Small strategy contract; shared builders own persistence and SDK policy."""
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class OnboardingStrategy:
    name: str
    assets: Path
    read_config: Callable
    render_adapter: Callable
    validate_plan: Callable
    validate_manifest: Callable
    stage_validation: Callable
    validate_selection: Callable
    validate_unit: Callable
    binding_steps: Callable
    version: str = "1"

    @property
    def manifest_schema(self):
        return self.assets / "manifest/analysis.schema.json"

    def requirements(self):
        return (self.assets / "manifest" / f"adapter-{self.name}.md").read_text()
