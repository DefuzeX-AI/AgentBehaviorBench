"""Manually supply Deep Researcher Agent's pinned source, materializing internal directory links.

Usage: python prepare_source.py /absolute/path/to/clean/pinned/deep-researcher-agent/checkout
The destination agent/ must not exist. Nothing in the source checkout is changed.
"""
from pathlib import Path
import hashlib
import shutil
import subprocess
import sys

REVISION = "951a1a1114e9818073ddbe2a5fdbfa824751f4d3"


def materialize(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; preserve it before preparing a new copy")
    toplevel = subprocess.check_output(["git", "-C", str(source), "rev-parse", "--show-toplevel"], text=True).strip()
    if Path(toplevel).resolve() != source:
        raise ValueError("Source must be the complete Git checkout root")
    revision = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    if revision != REVISION:
        raise ValueError("Source checkout does not match the pinned revision")
    dirty = subprocess.check_output(["git", "-C", str(source), "status", "--porcelain", "--untracked-files=all", "--ignored"], text=True)
    if dirty:
        raise ValueError("Source checkout must be clean, including untracked and ignored files")
    # Resolve every link before copying; reject escapes and recursive ancestors.
    for path in source.rglob("*"):
        if ".git" in path.relative_to(source).parts or not path.is_symlink():
            continue
        target = path.resolve(strict=True)
        if not target.is_relative_to(source) or path.parent.resolve().is_relative_to(target):
            raise ValueError("Source contains an unsafe or recursive symbolic link")
    shutil.copytree(source, destination, symlinks=False, ignore=shutil.ignore_patterns(".git"))
    # Compare all resulting regular files with their source targets, including
    # files reached through the one upstream directory link.
    for path in destination.rglob("*"):
        if path.is_symlink():
            raise ValueError("Prepared source unexpectedly contains a symbolic link")
        if path.is_file():
            original = source / path.relative_to(destination)
            if hashlib.sha256(path.read_bytes()).digest() != hashlib.sha256(original.read_bytes()).digest():
                raise ValueError("Prepared source differs from its pinned source file")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python prepare_source.py /absolute/path/to/pinned/deep-researcher-agent")
    materialize(Path(sys.argv[1]), Path(__file__).resolve().parent / "agent")
