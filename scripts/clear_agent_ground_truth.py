"""Clear outer Agent GT directories after a numeric cutoff, preserving .gitkeep.

Preview: python scripts/clear_agent_ground_truth.py --after 35
Apply:   python scripts/clear_agent_ground_truth.py --after 35 --apply
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import re
import shutil


def linked(path: Path) -> bool:
    return path.is_symlink() or bool(getattr(path.lstat(), 'st_file_attributes', 0) & 0x400)


def native(path: Path) -> str:
    """Support deeply nested archived evidence on Windows after validation."""
    value = str(path.absolute())
    prefix = chr(92) * 2 + '?' + chr(92)
    if os.name == 'nt' and not value.startswith(prefix):
        return prefix + ('UNC' + value[1:] if value.startswith(chr(92) * 2) else value)
    return value


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--after', type=int, default=35, help='Exclusive Agent number cutoff (default: 35)')
    parser.add_argument('--apply', action='store_true', help='Delete contents; otherwise only preview')
    args = parser.parse_args()
    agents = (Path(__file__).resolve().parents[1] / 'resources' / 'agents').resolve(strict=True)
    plans = []
    # Validate every destination before deleting anything. Only outer GT is in scope.
    for unit in sorted(agents.iterdir()):
        match = re.match(r'^(\d+)-', unit.name)
        if not match or int(match[1]) <= args.after or not unit.is_dir():
            continue
        if linked(unit) or unit.resolve().parent != agents:
            raise ValueError(f'Unsafe Agent directory: {unit}')
        gt = unit / 'ground_truth'
        if gt.exists() or gt.is_symlink():
            if linked(gt) or not gt.is_dir() or gt.resolve().parent != unit.resolve():
                raise ValueError(f'Unsafe GT directory: {gt}')
            contents = list(gt.iterdir())
        else:
            contents = []
        for child in contents:
            if child.name == '.gitkeep' and (linked(child) or not child.is_file()):
                raise ValueError(f'Unsafe placeholder: {child}')
            if not linked(child) and not child.resolve().is_relative_to(gt.resolve()):
                raise ValueError(f'GT deletion target outside intended directory: {child}')
        plans.append((gt, [p for p in contents if p.name != '.gitkeep']))
    for gt, contents in plans:
        print(f'{"CLEAR" if args.apply else "PREVIEW"} {gt.parent.name}: {len(contents)} entries', flush=True)
        if not args.apply:
            continue
        gt.mkdir(exist_ok=True)
        for child in contents:
            if linked(child):
                if child.is_symlink() or not child.is_dir():
                    child.unlink()
                else:
                    child.rmdir()  # Remove a junction itself, never its target.
            elif child.is_dir():
                shutil.rmtree(native(child))
            else:
                child.unlink()
        (gt / '.gitkeep').touch(exist_ok=True)
        if sorted(p.name for p in gt.iterdir()) != ['.gitkeep']:
            raise RuntimeError(f'GT directory was not fully cleared: {gt}')
    print(f'{"Cleared" if args.apply else "Selected"} {len(plans)} Agent GT directories after {args.after}.', flush=True)


if __name__ == '__main__':
    main()
