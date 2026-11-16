"""Native evidence references owned by ABB, shared by hosts and exporters.

Only ABB OTel envelopes define abb.*_ref attributes. Business JSON is opaque.
Historical recovery requires identical recorded span envelopes, never time or text matching.
"""
import hashlib
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from .view_api import RunViewAPI


class EvidenceChanged(ValueError):
    """A live writer changed bytes; callers may retry without accepting mixed data."""


def evidence_path(root, name):
    relative = PurePosixPath(name)
    if not name or relative.is_absolute() or PureWindowsPath(name).drive or ".." in relative.parts or "\\" in name:
        raise ValueError("Unsafe native evidence path")
    path = Path(root)
    if path.is_symlink():
        raise ValueError("Symlink evidence root")
    for part in relative.parts:
        path = path / part
        if path.is_symlink():
            raise ValueError("Symlink native evidence path")
    return path


def read_stable(root, name):
    path = evidence_path(root, name)
    before = path.stat()
    raw = path.read_bytes()
    after = path.stat()
    if (before.st_size, before.st_mtime_ns, before.st_ino) != (after.st_size, after.st_mtime_ns, after.st_ino) or len(raw) != after.st_size:
        raise EvidenceChanged("Native evidence changed while reading")
    return raw


def _otel_records(root, *, allow_incomplete=False):
    for folder in RunViewAPI(Path(root)).outputs():
        for filename in ("otel.jsonl", "otel-live.jsonl"):
            name = folder + "/" + filename
            path = evidence_path(root, name)
            if not path.exists():
                continue
            try:
                raw = read_stable(root, name)
            except EvidenceChanged:
                if allow_incomplete:
                    continue
                raise
            if allow_incomplete and raw and not raw.endswith(b"\n"):
                raw = raw.rsplit(b"\n", 1)[0] if b"\n" in raw else b""
            for line in raw.splitlines():
                if not line.strip():
                    continue
                row = json.loads(line)
                if isinstance(row, dict) and row.get("source") == "otel" and row.get("event") == "span":
                    yield name, row


def native_references(root, *, allow_incomplete=False):
    result = []
    for name, row in _otel_records(root, allow_incomplete=allow_incomplete):
        attributes = row.get("data", {}).get("attributes", {})
        for field, value in attributes.items():
            if field.startswith("abb.") and field.endswith("_ref"):
                if not isinstance(value, str):
                    raise ValueError("Invalid native evidence reference")
                evidence_path(root, value)  # Validate before joining with the origin.
                target = (PurePosixPath(name).parent / value).as_posix()
                evidence_path(root, target)
                result.append({"source": name, "field": field, "path": target})
    return result


def payload_paths(root, *, allow_incomplete=False):
    names = {item["path"] for item in native_references(root, allow_incomplete=allow_incomplete)}
    for folder in RunViewAPI(Path(root)).outputs():
        directory = evidence_path(root, folder + "/otel-payloads")
        if directory.exists():
            for path in directory.iterdir():
                name = path.relative_to(root).as_posix()
                path = evidence_path(root, name)
                if path.is_file():
                    names.add(name)
    return sorted(names)


def validate_native_references(root):
    refs = native_references(root)
    for item in refs:
        try:
            read_stable(root, item["path"])
        except FileNotFoundError:
            raise ValueError("Missing native evidence: " + item["path"]) from None
    return {"references_verified": len(refs), "payload_files": len({r["path"] for r in refs})}


def recover_payloads(source, target):
    """Repair a host snapshot from retained originals, without editing the originals.

    The host must supply an ended snapshot. Source span envelopes must match the
    snapshot exactly (formatting aside). Return explicit recovery provenance.
    """
    source, target = Path(source), Path(target)
    refs = native_references(target)
    missing = [r for r in refs if not evidence_path(target, r["path"]).is_file()]
    if not missing:
        validate_native_references(target)
        return []
    sources = {r["source"] for r in missing}
    frozen = {}
    for name in sources:
        original = read_stable(source, name)
        recorded = read_stable(target, name)
        if [json.loads(x) for x in original.splitlines() if x.strip()] != [json.loads(x) for x in recorded.splitlines() if x.strip()]:
            raise ValueError("Native evidence source differs from recorded snapshot: " + name)
        frozen[name] = original
    recovered = []
    for name in sorted({r["path"] for r in missing}):
        data = read_stable(source, name)
        frozen[name] = data
        path = evidence_path(target, name)
        if path.exists():
            if read_stable(target, name) != data:
                raise ValueError("Native evidence payload differs: " + name)
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        recovered.append({"path": name, "size": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                          "origin": "retained_native_evidence"})
    for name, data in frozen.items():
        if read_stable(source, name) != data:
            raise ValueError("Native evidence changed during recovery")
    validate_native_references(target)
    return recovered
