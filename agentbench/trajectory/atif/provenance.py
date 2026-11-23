"""Snapshot historical evidence without consulting today's Agent registry."""
from pathlib import Path
import hashlib
import importlib.metadata
import json

from agentbench.observe.interactions import _files
from agentbench.observe.view_api import RunViewAPI
from agentbench.observe.evidence_inventory import agent_trace_files, payload_paths
from . import BUILDER_VERSION, HARBOR_COMMIT, SCHEMA_VERSION


def snapshot(root):
    api = RunViewAPI(Path(root))
    names = {name for name, _, _ in _files(api.directory)}
    names.update(("run.json", "request/target.json", "request/experiment.json", "session.json", "process.json"))
    for folder in api.evidence_outputs():
        names.update(f"{folder}/{name}" for name in ("acp-events.jsonl", "acp-summary.json", "otel-status.json", "otel.jsonl", "otel-live.jsonl"))
        parent = Path(folder).parent
        names.add((parent / "input/execution-environment.json").as_posix())
    names.update(agent_trace_files(api.directory))
    names.update(payload_paths(api.directory))
    for path in (api.directory / "request").glob("native-config-*.yaml"):
        names.add(path.relative_to(api.directory).as_posix())
    result = {}
    for name in sorted(names):
        try:
            path = api.file(name)
        except FileNotFoundError:
            continue
        if not path.is_file():
            continue
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        result[path.relative_to(api.directory).as_posix()] = digest.hexdigest()
    return dict(sorted(result.items()))


def ensure_unchanged(bundle):
    if snapshot(bundle.root) != bundle.snapshot:
        raise ValueError("Source evidence changed during export")


def official_dependency():
    dist = importlib.metadata.distribution("harbor")
    direct = json.loads(dist.read_text("direct_url.json") or "{}")
    commit = direct.get("vcs_info", {}).get("commit_id")
    if commit != HARBOR_COMMIT:
        raise ValueError("ATIF experiment requires the pinned official Harbor commit")
    return {"version": dist.version, "commit": commit}


def provenance(bundle):
    architecture = bundle.target.get("architecture") or {}
    code_root = Path(__file__).parent
    code = {p.relative_to(code_root).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(code_root.rglob("*.py"))}
    native_reader = code_root.parent / "agent_otel.py"
    code["trajectory/agent_otel.py"] = hashlib.sha256(native_reader.read_bytes()).hexdigest()
    return {
        "schema_version": SCHEMA_VERSION, "builder_version": BUILDER_VERSION,
        "harbor": official_dependency(), "sources": bundle.snapshot,
        "converter_sources": code,
        "run_id": bundle.run.get("run_id"),
        "agent_revision": architecture.get("source_revision"),
        "collector_version": bundle.run.get("collector_version"),
        "image_id": bundle.run.get("image_id"),
        "target": bundle.target,
        "unavailable_provenance": [key for key in ("collector_version", "image_id") if not bundle.run.get(key)],
    }
