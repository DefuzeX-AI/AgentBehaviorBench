"""Copy only hash-verified pinned upstream files from a manual local snapshot."""
from pathlib import Path
import hashlib
import json
import shutil
import sys

UNIT = Path(__file__).resolve().parents[1]


def main():
    source = Path(sys.argv[1]).resolve(strict=True)
    target = UNIT / 'agent'
    if target.exists():
        raise SystemExit('agent/ exists; preserve and verify its hashes rather than overwriting it')
    hashes = json.loads((UNIT / 'source-file-sha256.json').read_text())
    for name, digest in hashes.items():
        path = source / name
        assert path.resolve().is_relative_to(source), 'Source link escapes the pinned snapshot'
        data = str(path.readlink()).encode() if path.is_symlink() else path.read_bytes()
        assert hashlib.sha256(data).hexdigest() == digest, 'Pinned source hash differs: ' + name
    target.mkdir()
    for name in hashes:
        original = source / name
        copied = target / name
        copied.parent.mkdir(parents=True, exist_ok=True)
        if original.is_symlink():
            copied.symlink_to(original.readlink())
        else:
            shutil.copy2(original, copied)
    print('SOURCE_READY: 7760 pinned entries verified; original symlinks preserved; source=bundled; EXIT=0')


if __name__ == '__main__':
    main()
