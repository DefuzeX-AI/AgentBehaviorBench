"""Keep generation records outside distributable Agent units."""
from hashlib import sha256
from pathlib import Path
from .writer import confined


def records_directory(unit: Path, registry: Path) -> Path:
    root = registry.resolve().parent.parent
    relative = unit.resolve().relative_to(root).as_posix()
    identity = sha256(relative.encode()).hexdigest()[:12]
    return confined(root, f"cache/onboarding/{unit.name}-{identity}")
