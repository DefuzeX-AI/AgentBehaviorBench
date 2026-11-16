"""Explicit offline conversion. No Docker, provider calls, or source writes."""
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import tempfile

from .reader import read_evidence
from .hierarchy import resolve_hierarchy
from .assembler import assemble_atif
from .provenance import provenance, ensure_unchanged
from .validation import validate_export
from .contracts import ExportResult


def build_export(directory, *, adapters=(), allow_incomplete=False):
    bundle = read_evidence(directory, allow_incomplete=allow_incomplete)
    graph = resolve_hierarchy(bundle, adapters=adapters)
    metadata = provenance(bundle)
    document = assemble_atif(bundle, graph, metadata)
    association, report = validate_export(bundle, graph, document)
    ensure_unchanged(bundle)
    return ExportResult(document, association, report, metadata), bundle


def save_json(path, value):
    path = Path(path)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=path.parent,
                                     prefix=".atif-", delete=False) as stream:
        temporary = Path(stream.name)
        try:
            json.dump(value, stream, ensure_ascii=False, indent=2, allow_nan=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def export_run(directory, output, *, adapters=(), allow_incomplete=False):
    source, destination = Path(directory).resolve(strict=True), Path(output).resolve()
    if destination == source or destination.is_relative_to(source) or source.is_relative_to(destination):
        raise ValueError("Export directory must be separate from source evidence")
    if Path(output).is_symlink() or destination.exists() and any(destination.iterdir()):
        raise ValueError("Export directory must be new or empty")
    destination.mkdir(parents=True, exist_ok=True)
    try:
        result, bundle = build_export(source, adapters=adapters, allow_incomplete=allow_incomplete)
        manifest = {**result.manifest, "adapters": list(adapters), "allow_incomplete": allow_incomplete,
                    "exported_at": datetime.now(timezone.utc).isoformat()}
        save_json(destination / "export-manifest.json", manifest)
        save_json(destination / "association-report.json", result.association)
        save_json(destination / "validation-report.json", result.validation)
        ensure_unchanged(bundle)
        # Publish the ATIF document last. Reports alone never signify success.
        save_json(destination / "trajectory.atif.json", result.document.to_json_dict())
        return result
    except Exception as exc:
        from agentbench.observe.store import redact, environment_secrets
        save_json(destination / "validation-report.json", {"status": "failed", "error_type": type(exc).__name__, "error": redact(str(exc), environment_secrets())})
        raise
