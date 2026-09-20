"""Inspect source readiness consistently for new and reused Agent checkouts."""
import os
from pathlib import Path


def checkout_warnings(source: Path, submodules=()) -> list[str]:
    """Report incomplete vendored dependencies and unsupported build symlinks."""
    submodules = submodules if isinstance(submodules, (list, tuple)) else ()
    missing = [item['path'] for item in submodules
               if isinstance(item, dict) and item.get('initialized') is False
               and isinstance(item.get('path'), str)]
    warnings = (["Submodules left empty, so the vendored source is incomplete: " + ", ".join(missing)]
                if missing else [])
    return warnings + _symlink_warning(source)


def _symlink_warning(source: Path) -> list[str]:
    links = []
    for directory, directories, files in os.walk(source, followlinks=False):
        for name in [*directories, *files]:
            if Path(directory, name).is_symlink():
                links.append(Path(directory, name).relative_to(source).as_posix())
    if not links:
        return []
    shown = ", ".join(sorted(links)[:5]) + (f" and {len(links) - 5} more" if len(links) > 5 else "")
    return [f"{len(links)} symlink(s) kept; build snapshots materialize in-tree file links; "
            f"directory, external or broken links need review: {shown}"]
