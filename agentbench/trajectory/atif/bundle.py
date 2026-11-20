"""Opt-in ATIF + portable trace publication; no collector or ownership changes."""
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import re
import shutil
import tempfile

from harbor.models.trajectories import Trajectory
from .reader import read_evidence
from .hierarchy import resolve_hierarchy
from .validation import evidence_report
from .export import build_export, save_json
from .evidence_store import EvidenceStore, EvidenceResolver, digest, json_bytes, safe_path, preserve_bytes, restore_bytes
from .provenance import ensure_unchanged
from agentbench.observe.evidence_inventory import validate_native_references

BUNDLE_FORMAT = "abb.portable-trace.v1"


def _write_json(store, path, value, *, pretty=False):
    if pretty:
        text = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
        data = (text + "\n").encode("utf-8")
    else:
        data = json_bytes(value)
    return store.write(data, path, media="application/json")


def _summary(record):
    fields = ("id", "kind", "call_id", "tool_call_id", "invocation_id", "run_id", "case_id", "attempt_id",
              "input_id", "native_session_id", "span", "source", "timestamp", "ended_at", "status",
              "execution_status", "identity_conflicts", "name", "tool_name", "error")
    result = {key: record[key] for key in fields if key in record}
    if record["kind"] == "model":
        result["output"] = record.get("client_output") or record.get("output")
    else:
        result.update(input_arguments=record.get("input_arguments"), outputs=record.get("outputs"))
    return result


def _walk_json(doc):
    yield doc
    for child in doc.get("subagent_trajectories") or []:
        yield from _walk_json(child)


def compact_document(original, store, calls, owners, results):
    """Preserve official fields verbatim; externalize ABB diagnostic copies."""
    doc = deepcopy(original)
    def extra(target, default_refs=()):
        previous = target.get("extra")
        if not previous:
            target["extra"] = {"abb": {"evidence_refs": list(default_refs)}}
            return
        details = store.value(previous)
        abb = previous.get("abb", {})
        ids = abb.get("record_ids", [])
        references = [calls[rid] for rid in ids if rid in calls]
        if "result_source" in abb:
            references.append(store.value(results[abb["result_source"]]))
        references = references or [details]
        small = {"evidence_refs": references, "details_ref": details}
        for key in ("record_ids", "kind", "association", "version_missing_reason", "result_source"):
            if key in abb:
                small[key] = abb[key]
        if "execution_start" in abb:
            small["execution_started_at"] = abb["execution_start"]["start_time"]
        if "execution" in abb:
            execution = abb["execution"]
            small["execution"] = {key: execution[key] for key in ("key", "name", "parent_id", "boundary_id", "status") if key in execution}
        if abb.get("unassigned_records"):
            small["unassigned_records"] = [{**_summary(record), "evidence_refs": [calls[record["id"]]], "ownership": "unknown"}
                                            for record in abb["unassigned_records"]]
        target["extra"] = {"abb": small}
    for trajectory in _walk_json(doc):
        owned = [calls[rid] for rid in sorted(calls) if owners.get(rid) == trajectory["trajectory_id"]]
        first_model_ids = next(((step.get("extra") or {}).get("abb", {}).get("record_ids", [])
            for step in trajectory["steps"] if "model_record" in (step.get("extra") or {}).get("abb", {})), [])
        defaults = [calls[rid] for rid in first_model_ids if rid in calls] or owned[:1]
        for step in trajectory["steps"]:
            extra(step, defaults)
            for observation in (step.get("observation") or {}).get("results", []):
                extra(observation, defaults)
        extra(trajectory, defaults)
    Trajectory.model_validate(doc)
    return doc


def restore_document(doc, resolver):
    restored = deepcopy(doc)
    def extra(target):
        abb = (target.get("extra") or {}).get("abb", {})
        if "details_ref" in abb:
            target["extra"] = resolver.resolve(abb["details_ref"])
        elif set(abb) == {"evidence_refs"}:
            target.pop("extra", None)
    for trajectory in _walk_json(restored):
        extra(trajectory)
        for step in trajectory["steps"]:
            extra(step)
            for observation in (step.get("observation") or {}).get("results", []):
                extra(observation)
    return restored


def _reserve(parent, stem):
    """Reserve a name with O_EXCL; rename only into our own reserved destination."""
    for number in range(1, 1000000):
        name = stem if number == 1 else f"{stem}-{number}"
        destination, reservation = parent / name, parent / ("." + name + ".reservation")
        if destination.exists() or destination.is_symlink():
            continue
        try:
            fd = os.open(reservation, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            continue
        os.close(fd)
        if destination.exists() or destination.is_symlink():
            reservation.unlink()
            continue
        return destination, reservation
    raise ValueError("Unable to reserve a new export directory")


def export_bundle(directory, output, *, adapters=(), allow_incomplete=False, evidence_files=()):
    """Export into a new run-XXXXXXXX child of output; return its path and report.

Additional evidence files must be explicitly declared by the caller (for example
verified workspace outputs). Never recursively copy a run or its proxy cache.
"""
    evidence_files = tuple(evidence_files)
    source, parent = Path(directory).resolve(strict=True), Path(output).resolve()
    if parent == source or parent.is_relative_to(source) or source.is_relative_to(parent):
        raise ValueError("Export directory must be separate from source evidence")
    if Path(output).is_symlink():
        raise ValueError("Export parent cannot be a symbolic link")
    parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(tempfile.mkdtemp(prefix=".trace-staging-", dir=parent))
    reservation = None
    try:
        validate_native_references(source)
        result, native = build_export(source, adapters=adapters, allow_incomplete=allow_incomplete)
        bundle = read_evidence(source, allow_incomplete=allow_incomplete)
        if native.snapshot != bundle.snapshot:
            raise ValueError("Source evidence changed during export")
        trace_graph = resolve_hierarchy(bundle, adapters=adapters)
        trace_association, coverage = evidence_report(bundle, trace_graph, result.document)
        frozen = dict(bundle.snapshot)
        for name in evidence_files:
            frozen[name] = digest(safe_path(source, name).read_bytes())
        store = EvidenceStore(temporary)
        calls, events, operations = {}, [], {}
        raw_by_position = {(r["file"], r["line"]): r for r in bundle.raw_records}
        # Register actual wire bodies before structured views, allowing exact
        # source/outbound equality to share readable request/response paths.
        for kind, records in (("model", bundle.models), ("tool", bundle.tools)):
            for number, record in enumerate(sorted(records, key=lambda r: r["id"]), 1):
                base = f"runs/{kind}-calls/{number:04d}"
                body_refs = {}
                if kind == "model":
                    for field, label in (("raw_request", "request"), ("raw_response", "response")):
                        raw = record.get(field) or {}
                        for key in ("raw_body", "source_raw_body", "client_raw_body"):
                            if isinstance(raw.get(key), str):
                                suffix = "" if key == "raw_body" else "-" + key.removesuffix("_raw_body")
                                body_refs[field + "." + key] = store.raw_body(raw[key], base + "/" + label + suffix)
                        if not body_refs or not any(k.startswith(field + ".") for k in body_refs):
                            body_refs[field] = store.value(raw, base + "/" + label + ".json")
                    stream_rows = [raw_by_position[(ref["file"], ref["line"])]
                        for ref in record.get("evidence", []) if (ref["file"], ref["line"]) in raw_by_position
                        and isinstance(raw_by_position[(ref["file"], ref["line"])]["raw"], dict)
                        and raw_by_position[(ref["file"], ref["line"])]["raw"].get("event") == "llm_delta"]
                    if stream_rows:
                        packed = [store.pack(frame) for frame in stream_rows]
                        body_refs["stream"] = {"path": store.write(b"".join(json_bytes(p) + b"\n" for p in packed), base + "/stream-events.jsonl", media="application/x-ndjson"), "encoding": "jsonl-values"}
                else:
                    for key, name in (("input_arguments", "arguments"), ("outputs", "result")):
                        body_refs[key] = store.value(record.get(key), base + "/" + name + (".txt" if isinstance(record.get(key), str) else ".json"))
                ref = store.value(record, base + "/record.json")
                call = {"record_id": record["id"], "kind": kind,
                        "owner": trace_graph.owners[record["id"]],
                        "record_ref": ref, "body_refs": body_refs,
                        "representation": "structured_observation", "identity": {k: v for k, v in _summary(record).items() if k != "output" and k != "outputs" and k != "input_arguments"}}
                path = _write_json(store, base + "/call.json", call)
                calls[record["id"]] = {"path": path, "encoding": "json"}
                operations[record["id"]] = {"kind": kind, "owner": call["owner"], "ref": ref}
                events.append({"kind": kind, "record_id": record["id"], "timestamp": record.get("timestamp"), "evidence_ref": calls[record["id"]]})
        # Source identity is its recorded file, not a guessed framework label.
        by_file = {}
        for raw in sorted(bundle.raw_records, key=lambda r: (r["file"], r["line"])):
            by_file.setdefault(raw["file"], []).append(raw)
        source_entries, raw_checks = [], []
        for number, (name, expected_hash) in enumerate(sorted(frozen.items()), 1):
            data = safe_path(source, name).read_bytes()
            if digest(data) != expected_hash:
                raise ValueError("Source evidence changed during export")
            base = f"runs/sources/source-{number:04d}"
            rows = by_file.get(name, [])
            packed_rows = [store.pack(row) for row in rows]
            records_path = store.write(b"".join(json_bytes(row) + b"\n" for row in packed_rows), base + "/records.jsonl", media="application/x-ndjson") if rows else None
            for line, raw in enumerate(rows, 1):
                ref = {"path": records_path, "line": line, "encoding": "jsonl-value"}
                raw_checks.append({"file": raw["file"], "line": raw["line"], "sha256": digest(json_bytes(raw)), "ref": ref})
                events.append({"kind": "source_record", "source_file": name, "source_line": raw["line"], "timestamp": raw["raw"].get("timestamp") if isinstance(raw["raw"], dict) else None, "evidence_ref": ref})
            pieces = data.splitlines(keepends=True) if name.endswith(".jsonl") else [data]
            if name in evidence_files:
                encodings = [{"representation": "opaque", "ref": store.literal(data, "runs/files/" + name)}]
            else:
                encodings = [preserve_bytes(store, part, base + f"/original-{i:06d}", pooled=True) for i, part in enumerate(pieces, 1)]
            source_entries.append({"source_id": f"source-{number:04d}", "original_path": name,
                "size": len(data), "sha256": expected_hash, "records_path": records_path,
                "observed_source_labels": sorted({str(row["raw"]["source"]) for row in rows if isinstance(row["raw"], dict) and row["raw"].get("source") is not None}),
                "pieces_ref": store.value(encodings, base + "/original-layout.json")})
        event_path = store.write(b"".join(json_bytes(e) + b"\n" for e in events), "runs/events.jsonl", media="application/x-ndjson")
        original = result.document.to_json_dict()
        results = {item["folder"] + "/result.json": item["result"] for item in bundle.inputs}
        # Native model records can have different IDs from joined trace records.
        # Resolve those references to the actual callback payload under runs/.
        native_refs = {r["id"]: calls.get(r["id"]) or store.value(r) for r in native.models + native.tools}
        doc = compact_document(original, store, native_refs, result.association["owners"], results)
        doc["extra"]["abb"]["bundle_format"] = BUNDLE_FORMAT
        doc["extra"]["abb"]["events_ref"] = {"path": event_path, "encoding": "jsonl-events"}
        _write_json(store, "trajectory.json", doc, pretty=True)
        association_ref = store.value(trace_association, "runs/association.json")
        manifest = {"format": BUNDLE_FORMAT, "run_id": bundle.run["run_id"],
            "exported_at": datetime.now(timezone.utc).isoformat(), "adapters": list(adapters), "allow_incomplete": allow_incomplete,
            "provenance": result.manifest, "sources": source_entries, "raw_records": raw_checks,
            "operations": operations, "association_ref": association_ref, "coverage": coverage,
            "full_document_sha256": digest(json_bytes(original)),
            "excluded_categories": ["runtime_credentials", "proxy_private_keys", "runtime_caches", "ui_snapshots", "undeclared_files"],
            "files": store.files,
            "statistics": {"source_bytes": sum(s["size"] for s in source_entries),
                "legacy_atif_compact_bytes": len(json_bytes(original)), "stored_file_bytes": sum(f["size"] for f in store.files.values()),
                "reused_representation_bytes": store.reused_bytes}}
        ensure_unchanged(bundle)
        resolver = EvidenceResolver(temporary, store.files)
        # Compare against the actual frozen source, not merely our own success flag.
        for item in source_entries:
            restored = b"".join(restore_bytes(resolver, p) for p in resolver.resolve(item["pieces_ref"]))
            if restored != safe_path(source, item["original_path"]).read_bytes():
                raise ValueError("Original source bytes were not preserved")
        if restore_document(doc, resolver) != original:
            raise ValueError("ATIF diagnostics were not losslessly externalized")
        save_json(temporary / "manifest.json", manifest)
        from .bundle_validation import verify_bundle
        verified = verify_bundle(temporary)
        ensure_unchanged(bundle)
        for name, expected in frozen.items():
            if digest(safe_path(source, name).read_bytes()) != expected:
                raise ValueError("Source evidence changed during export")
        # Private staging directory becomes visible as a complete package in one
        # rename. The exclusive sibling reservation coordinates all exporters.
        stem_id = re.sub(r"[^A-Za-z0-9_-]", "", str(bundle.run["run_id"]))[:8] or digest(str(bundle.run["run_id"]).encode())[:8]
        destination, reservation = _reserve(parent, "run-" + stem_id)
        if destination.exists() or destination.is_symlink():
            raise ValueError("Export destination appeared during publication")
        from .publication import publish_directory
        publish_directory(temporary, destination)
        return {"path": str(destination), "validation": verified, "coverage": coverage, "statistics": manifest["statistics"]}
    except BaseException as exc:
        # No private evidence or exception strings are placed in failure reports.
        fd, report = tempfile.mkstemp(prefix="export-failed-", suffix=".json", dir=parent)
        os.close(fd)
        save_json(report, {"status": "failed", "error_type": type(exc).__name__, "published": False})
        raise
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
        if reservation:
            reservation.unlink(missing_ok=True)
