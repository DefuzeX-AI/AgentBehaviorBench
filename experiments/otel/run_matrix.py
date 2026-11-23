"""Audit registered Agents through ABB's observe runner and retain run-level evidence."""
import argparse
from collections import Counter
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
import json
import os
from pathlib import Path
import shutil
import sys
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from agentbench.cli.environment import load_project_environment
from agentbench.harness.otel.config import tomllib, parse_config
from agentbench.harness.otel.evidence import attribute_map
from agentbench.observe.catalog import resolve_agent
from agentbench.observe.service import observe
from agentbench.observe.store import environment_secrets, redact
from agentbench.runtime.agentcontainer.config import AgentContainerConfig
from agentbench.runtime.contracts.secrets import EnvironmentSecretResolver


def registration(entry):
    manifest = tomllib.loads((ROOT / entry["path"] / "agent.toml").read_text(encoding="utf-8"))
    config = parse_config(manifest)
    adapter = manifest["adapter"]
    return {"agent": entry["agent_id"], "manifest": entry["path"] + "/agent.toml",
            "revision": manifest.get("source", {}).get("revision"),
            "entrypoint": adapter.get("command") or adapter.get("binding") or adapter.get("entrypoint"),
            "framework": entry["framework"], "profile": config.profile, "profile_reason": config.reason,
            "status": "pending", "run_id": None, "directory": None, "span_count": 0}, manifest


def coverage(path):
    operations, scopes, bodies = set(), set(), set()
    origins = Counter()
    ids, parents = set(), set()
    refs = {}
    with path.open(encoding="utf-8") as stream:
        for n, line in enumerate(stream, 1):
            record = json.loads(line)
            if record["origin"] not in ("agent_native", "auto_instrumented"):
                continue
            origins[record["origin"]] += 1
            span = record["span"]
            attrs = attribute_map(span)
            scopes.add(record["scope"].get("name", ""))
            kind = attrs.get("gen_ai.operation.name") or attrs.get("openinference.span.kind") or "other"
            operations.add(kind)
            refs.setdefault(str(kind), {"file": "otel/spans.jsonl", "line": n,
                                        "trace_id": span["traceId"], "span_id": span["spanId"]})
            ids.add((span["traceId"], span["spanId"]))
            if span.get("parentSpanId"):
                parents.add((span["traceId"], span["parentSpanId"]))
            bodies.update(k for k in attrs if k in ("input.value", "output.value", "gen_ai.input.messages",
                "gen_ai.output.messages", "gen_ai.tool.call.arguments", "gen_ai.tool.call.result",
                "gen_ai.tool.call.input", "gen_ai.tool.call.output"))
    return dict(origin_counts=dict(origins), operations=sorted(operations), scopes=sorted(scopes), body_fields=sorted(bodies),
                has_model=bool(operations & {"LLM", "chat", "generate_content", "text_completion"}),
                has_tool=bool(operations & {"TOOL", "execute_tool"}), has_linked_parent=bool(parents & ids), evidence=refs)


def error_text(exc):
    message = str(redact(str(exc), environment_secrets()))
    return message if len(message) <= 1600 else message[:200] + "\n…\n" + message[-1350:]


def audit(row, entry, manifest, registry, results, args):
    agent = resolve_agent(entry, registry)
    # Fail on the same required credentials as the runtime before fetching large sources.
    AgentContainerConfig.from_agent_dir(agent.path, secret_resolver=EnvironmentSecretResolver())
    unit = results / "runs" / row["agent"] / uuid4().hex
    value = args.prompt
    adapter = manifest["adapter"]
    if adapter.get("input_key"):
        value = {adapter["input_key"]: value}
    elif entry["framework"] == "langgraph":
        fields = manifest.get("observe", {}).get("input_fields", [])
        value = {f["name"]: args.prompt for f in fields} if fields else args.prompt
    try:
        directory = observe(agent, value, output=unit, environ=dict(os.environ), timeout=args.timeout)
    except Exception as exc:
        row.update(status="blocked", reason=error_text(exc))
        directory = next((f.parent for f in unit.glob("*/run.json")), None)
    if directory is None:
        return
    run = json.loads((directory / "run.json").read_text(encoding="utf-8"))
    row.update(run_id=run["run_id"], directory=str(directory.relative_to(results)), execution=run["status"])
    status_file = directory / "otel/status.json"
    if not status_file.is_file():
        row.update(status="blocked")
        row.setdefault("reason", "Agent trace capture did not publish status")
        return
    capture = json.loads(status_file.read_text(encoding="utf-8"))
    row.update(capture=capture["status"], span_count=capture["span_count"])
    if row["span_count"]:
        row.update(coverage(directory / "otel/spans.jsonl"))
    if "reason" not in row:
        row["status"] = capture["status"]
        if capture.get("reason"):
            row["reason"] = capture["reason"]


def attempt(row, entry, manifest, registry, results, args):
    row = row.copy()
    try:
        audit(row, entry, manifest, registry, results, args)
    except Exception as exc:
        row.update(status="blocked", reason=error_text(exc))
    return row


def save(results, rows):
    target = results / "matrix.jsonl"
    temp = target.with_suffix(".tmp")
    temp.write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows), encoding="utf-8")
    temp.replace(target)
    counts = Counter(row["status"] for row in rows)
    lines = ["# Agent trace audit", "", f"{len(rows)} registered Agents.", ""]
    lines.extend(f"- {status} {n}" for status, n in sorted(counts.items()))
    received = [row for row in rows if row.get("span_count")]
    runs = sum(bool(row.get("run_id")) for row in rows)
    zero = sum(row.get("execution") == "succeeded" and row.get("capture") == "zero_spans" for row in rows)
    blocked_with_spans = sum(row["status"] == "blocked" for row in received)
    lines.extend(["", f"Runs with a run ID: {runs}. Agents with exported spans: {len(received)}.",
                  f"Of those Agents, {blocked_with_spans} retained evidence from a blocked or degraded run.",
                  f"Successful runs with a configured exporter and zero spans: {zero}.",
                  "Model, tool and body coverage below refers to fields present in the exported records."])
    if received:
        lines.append("Coverage by Agent: " + ", ".join(
            f"{sum(bool(row.get(key)) for row in received)} {label}" for key, label in
            (("has_model", "with model operations"), ("has_tool", "with tool operations"),
             ("body_fields", "with exported body fields"), ("has_linked_parent", "with matching parent span IDs"))) + ".")
    retries = [row["agent"] for row in rows if row.get("prior_attempts")]
    if retries:
        lines.append("Targeted reruns are included for " + ", ".join(retries) +
                     ". Their earlier attempt IDs and outcomes are retained in matrix.jsonl.")
    if received:
        lines.extend(["", "## Agent-exported evidence", "",
                      "| Agent | Run | Spans | Model | Tool | Body | Linked parent span |",
                      "| --- | --- | ---: | --- | --- | --- | --- |"])
        for row in received:
            link = f"[{row['run_id']}]({row['directory']}/otel/spans.jsonl)"
            flags = ["yes" if row.get(key) else "—" for key in
                     ("has_model", "has_tool", "body_fields", "has_linked_parent")]
            lines.append(f"| {row['agent']} | {link} | {row['span_count']} | " + " | ".join(flags) + " |")
    (results / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--agent", action="append", default=[])
    parser.add_argument("--timeout", type=int, default=300)
    parser.add_argument("--jobs", type=int, default=1, help="Maximum simultaneous isolated Agent runs")
    parser.add_argument("--prompt", default="Reply READY. Use no accounts or external tools.")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--min-free-gib", type=float, default=0, help="Pause before another build below this free space")
    args = parser.parse_args()
    if args.jobs < 1:
        parser.error("--jobs must be at least one")
    load_project_environment(ROOT / ".env")
    results = args.output.resolve()
    results.mkdir(parents=True, exist_ok=True)
    registry = ROOT / "resources/registry.toml"
    entries = tomllib.loads(registry.read_text(encoding="utf-8"))["agents"]
    records = {entry["agent_id"]: registration(entry) for entry in entries}
    unknown = set(args.agent) - records.keys()
    if unknown:
        parser.error(f"Unknown Agent IDs: {sorted(unknown)}")
    rows = {name: row for name, (row, _) in records.items()}
    output = results / "matrix.jsonl"
    if output.exists():
        for line in output.read_text(encoding="utf-8").splitlines():
            previous = json.loads(line)
            if previous["agent"] in rows:
                rows[previous["agent"]] = previous
    save(results, rows.values())
    queue = [entry for entry in entries if (not args.agent or entry["agent_id"] in args.agent)
             and (not args.resume or rows[entry["agent_id"]]["status"] == "pending")]
    running = set()
    with ProcessPoolExecutor(max_workers=args.jobs) as workers:
        while queue or running:
            while queue and len(running) < args.jobs and shutil.disk_usage(results).free / 2**30 >= args.min_free_gib:
                entry = queue.pop(0)
                row, manifest = records[entry["agent_id"]]
                running.add(workers.submit(attempt, row, entry, manifest, registry, results, args))
            if not running:
                print("Paused at configured disk reserve. Resume with --resume.", flush=True)
                return 2
            completed, running = wait(running, return_when=FIRST_COMPLETED)
            for task in completed:
                row = task.result()
                rows[row["agent"]] = row
                print(row["agent"], row["status"], flush=True)
            save(results, rows.values())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
