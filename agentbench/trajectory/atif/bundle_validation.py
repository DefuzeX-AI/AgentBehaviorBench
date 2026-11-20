"""Offline bundle verification using only package files, never the original run."""
from collections import Counter
from pathlib import Path
import json
import tempfile

from harbor.models.trajectories import Trajectory
from agentbench.observe.evidence_inventory import validate_native_references
from .evidence_store import EvidenceResolver, digest, json_bytes, safe_path, restore_bytes
from .bundle import BUNDLE_FORMAT, restore_document, _walk_json, _summary


def verify_bundle(directory):
    root = Path(directory)
    if root.is_symlink():
        raise ValueError("Bundle root cannot be a symbolic link")
    manifest = json.loads(safe_path(root, "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("format") != BUNDLE_FORMAT:
        raise ValueError("Unknown portable bundle format")
    resolver = EvidenceResolver(root, manifest["files"])
    actual = set()
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Bundle contains a symbolic link")
        if path.is_file():
            actual.add(path.relative_to(root).as_posix())
    if actual != set(manifest["files"]) | {"manifest.json"}:
        raise ValueError("Bundle file inventory mismatch")
    for name in manifest["files"]:
        resolver.bytes(name)
    jsonl_cache = {}
    def reference(ref):
        encoding = ref["encoding"]
        if encoding.startswith("jsonl-"):
            path = ref["path"]
            if path not in jsonl_cache:
                jsonl_cache[path] = [json.loads(line) for line in resolver.bytes(path).splitlines()]
            rows = jsonl_cache[path]
            if encoding == "jsonl-value":
                line = ref["line"]
                if type(line) is not int or not 1 <= line <= len(rows):
                    raise ValueError("Invalid evidence line reference")
                return resolver.unpack(rows[line - 1])
            if encoding == "jsonl-values":
                return [resolver.unpack(row) for row in rows]
            if encoding == "jsonl-events":
                return rows
            raise ValueError("Unknown JSONL reference encoding")
        return resolver.resolve(ref)
    doc = json.loads(resolver.bytes("trajectory.json"))
    Trajectory.model_validate(doc)
    for trajectory in _walk_json(doc):
        for target in [trajectory, *trajectory["steps"], *[observation for step in trajectory["steps"] for observation in (step.get("observation") or {}).get("results", [])]]:
            abb = (target.get("extra") or {}).get("abb", {})
            for ref in abb.get("evidence_refs", []):
                reference(ref)
            if "details_ref" in abb:
                reference(abb["details_ref"])
            for unknown in abb.get("unassigned_records", []):
                for ref in unknown["evidence_refs"]:
                    reference(ref)
    events = reference(doc["extra"]["abb"]["events_ref"])
    for event in events:
        value = reference(event["evidence_ref"])
        if event["kind"] != "source_record":
            recorded = reference(value["record_ref"])
            if recorded["id"] != event["record_id"] or value["record_id"] != recorded["id"]:
                raise ValueError("Call reference points to another operation")
            if value["owner"] != manifest["operations"][recorded["id"]]["owner"]:
                raise ValueError("Call ownership metadata differs")
            for field, ref in value["body_refs"].items():
                content = reference(ref)
                if field == "stream":
                    expected_positions = {(r["file"], r["line"]) for r in recorded["evidence"]}
                    if any((r["file"], r["line"]) not in expected_positions or r["raw"].get("event") != "llm_delta" for r in content):
                        raise ValueError("Stream event belongs to another call")
                else:
                    expected = recorded
                    for part in field.split("."):
                        expected = expected.get(part)
                    if json_bytes(content) != json_bytes(expected):
                        raise ValueError("Call body reference content differs")
    original = restore_document(doc, resolver)
    unknown = {r["id"]: r for r in original["extra"]["abb"]["unassigned_records"]}
    shown = doc["extra"]["abb"].get("unassigned_records", [])
    if Counter(r["id"] for r in shown) != Counter(unknown.keys()):
        raise ValueError("Unassigned display records were lost or duplicated")
    for row in shown:
        if {k:v for k,v in row.items() if k not in ("evidence_refs", "ownership")} != _summary(unknown[row["id"]]) or row["ownership"] != "unknown":
            raise ValueError("Unassigned display content differs from evidence")
    if digest(json_bytes(original)) != manifest["full_document_sha256"]:
        raise ValueError("Restored ATIF content mismatch")
    raw = []
    for expected in manifest["raw_records"]:
        row = reference(expected["ref"])
        if row["file"] != expected["file"] or row["line"] != expected["line"] or digest(json_bytes(row)) != expected["sha256"]:
            raise ValueError("Original record identity/content mismatch")
        raw.append(row)
    if len({(r["file"], r["line"]) for r in raw}) != len(raw):
        raise ValueError("Duplicate source record identity")
    expected_operations = Counter(manifest["operations"].keys())
    if Counter(event["record_id"] for event in events if event["kind"] != "source_record") != expected_operations:
        raise ValueError("Operation events were lost or duplicated")
    if Counter((event["source_file"], event["source_line"]) for event in events if event["kind"] == "source_record") != Counter((r["file"], r["line"]) for r in raw):
        raise ValueError("Source events were lost or duplicated")
    # Reconstruct the frozen run in an isolated temporary directory. Readers and
    # the existing identity resolver verify semantics; no external artifacts,
    # current registry, network access, Docker or provider calls are involved.
    with tempfile.TemporaryDirectory(prefix="abb-bundle-verify-") as temporary:
        reconstructed = Path(temporary)
        seen = set()
        for source in manifest["sources"]:
            name = source["original_path"]
            if name in seen:
                raise ValueError("Duplicate source file identity")
            seen.add(name)
            data = b"".join(restore_bytes(resolver, part) for part in resolver.resolve(source["pieces_ref"]))
            if len(data) != source["size"] or digest(data) != source["sha256"]:
                raise ValueError("Original source byte mismatch")
            path = safe_path(reconstructed, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        native_validation = validate_native_references(reconstructed)
        from .reader import read_evidence
        from .hierarchy import resolve_hierarchy
        from .validation import validate_export, evidence_report
        from .validation import content_checks
        bundle = read_evidence(reconstructed, allow_incomplete=manifest["allow_incomplete"])
        results = {item["folder"] + "/result.json": item["result"] for item in bundle.inputs}
        for step, restored_step in zip(doc["steps"], original["steps"]):
            abb = (step.get("extra") or {}).get("abb", {})
            source = (restored_step.get("extra") or {}).get("abb", {}).get("result_source")
            if source or "result_source" in abb:
                if (source not in results or abb.get("result_source") != source
                        or not any(reference(ref) == results[source] for ref in abb.get("evidence_refs", []))):
                    raise ValueError("Invocation reply evidence reference mismatch")
        graph = resolve_hierarchy(bundle, adapters=manifest["adapters"])
        restored_model = Trajectory.model_validate(original)
        native = bundle
        if manifest["provenance"].get("builder_version", 0) >= 4:
            native = read_evidence(reconstructed, allow_incomplete=manifest["allow_incomplete"], include_network=False)
        native_graph = graph if native is bundle else resolve_hierarchy(native, adapters=manifest["adapters"])
        validate_export(native, native_graph, Trajectory.model_validate(doc), evidence_resolver=resolver)
        association, coverage = evidence_report(bundle, graph, restored_model)
        # Compiler provenance/issues may evolve; identity and source content may not.
        saved = resolver.resolve(manifest["association_ref"])
        for key in ("owners", "tool_relations", "raw_record_owners"):
            if association[key] != saved[key]:
                raise ValueError("Association changed after portable reconstruction")
        checks = content_checks(native, restored_model)
        if not all(c["passed"] for c in checks):
            raise ValueError("Model or tool content differs from frozen source")
        observed = {r["id"]: r for r in bundle.models + bundle.tools}
        if set(observed) != set(manifest["operations"]):
            raise ValueError("Operation coverage mismatch")
        for rid, item in manifest["operations"].items():
            if json_bytes(resolver.resolve(item["ref"])) != json_bytes(observed[rid]) or item["owner"] != graph.owners[rid]:
                raise ValueError("Operation content/ownership mismatch")
        if {(r["file"], r["line"]): json_bytes(r) for r in bundle.raw_records} != {(r["file"], r["line"]): json_bytes(r) for r in raw}:
            raise ValueError("Raw records differ from reconstructed source")
    return {"passed": True, "native_references": native_validation, "official_schema_valid": True, "source_bytes_preserved": True,
            "records_reconstructed": len(raw), "content_checks": len(checks),
            "files_verified": len(manifest["files"]), "models": coverage["observed_models"],
            "tools": coverage["observed_tools"], "children": coverage["embedded_children"],
            "assigned": coverage["assigned_records"], "unassigned": coverage["unassigned_records"]}
