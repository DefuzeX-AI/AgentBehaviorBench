"""Restore only checkout conversions proven against the pinned Git blobs."""
import hashlib
import json
from pathlib import Path

root = Path("/opt/agent/agent").resolve()
manifest = json.loads(Path("/tmp/checkout-format.json").read_text())

def target(relative):
    path = (root / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError("Checkout metadata path escapes the source directory")
    return path

def git_blob(data):
    return hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()

absent = set()
for item in manifest["normalize"]:
    path = target(item["path"])
    if not path.exists():
        absent.add(item["path"])
        continue
    data = path.read_bytes()
    if git_blob(data) == item["sha"]:
        continue
    canonical = data.replace(b"\r\n", b"\n")
    if git_blob(canonical) != item["sha"]:
        raise ValueError("Source differs from the pinned Git blob: " + item["path"])
    path.write_bytes(canonical)
for relative in manifest["executable"]:
    path = target(relative)
    if not path.exists():
        absent.add(relative)
        continue
    path.chmod(path.stat().st_mode | 0o111)
print("Restored pinned upstream line endings and executable modes")
print("Files not present in staged build context:", len(absent), sorted(absent)[:10])
