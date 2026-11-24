"""Internal evidence values, not an alternative public trajectory schema."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
import hashlib
import json


def stable_id(*parts):
    return hashlib.sha256(json.dumps(parts, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class EvidenceRef:
    file: str
    line: int | None
    digest: str


@dataclass(frozen=True)
class ExecutionKey:
    run_id: str
    invocation_id: str | None
    source: str
    native_id: str
    run_scope: dict = field(default_factory=dict)
    native_session_id: str | None = None
    source_file: str | None = None

    @property
    def id(self):
        return stable_id(asdict(self))


def execution_key(bundle, invocation_id, source, native_id, **kwargs):
    scope = {name: bundle.run[name] for name in
             ("case_id", "attempt_id", "attempt_number", "artifact_run_id", "suite_id")
             if bundle.run.get(name) is not None}
    return ExecutionKey(bundle.run["run_id"], invocation_id, source, native_id, scope, **kwargs)


@dataclass
class EvidenceIssue:
    code: str
    message: str
    record_ids: list[str] = field(default_factory=list)


@dataclass
class ExecutionNode:
    key: ExecutionKey
    name: str
    parent_id: str | None = None
    boundary_id: str | None = None
    input: Any = None
    evidence: list[dict] = field(default_factory=list)
    record_ids: list[str] = field(default_factory=list)
    status: str = "unknown"


@dataclass
class DelegationLink:
    parent_id: str | None
    child_id: str
    tool_id: str
    evidence: list[dict] = field(default_factory=list)


@dataclass
class DelegationEvidence:
    nodes: list[ExecutionNode] = field(default_factory=list)
    links: list[DelegationLink] = field(default_factory=list)
    issues: list[EvidenceIssue] = field(default_factory=list)
    facts: list[dict] = field(default_factory=list)
    # record id -> id of a record whose execution it continues
    same_execution: dict[str, str] = field(default_factory=dict)


@dataclass
class EvidenceBundle:
    root: Path
    run: dict
    snapshot: dict
    inputs: list[dict]
    models: list[dict]
    tools: list[dict]
    spans: dict[str, dict]
    native_events: list[dict]
    issues: list[EvidenceIssue]
    target: dict = field(default_factory=dict)
    raw_records: list[dict] = field(default_factory=list)
    auxiliary_artifacts: dict = field(default_factory=dict)
    unassigned_agent_spans: list[dict] = field(default_factory=list)
    # The step source that read the records; whether it projects the delivered
    # result as a step of its own; whether Agent-exported spans are its steps.
    source: str = "langgraph"
    reply_steps: bool = True
    exported_steps: bool = False


@dataclass
class ExecutionGraph:
    root_id: str
    nodes: dict[str, ExecutionNode]
    owners: dict[str, str | None]
    delegations: list[DelegationLink]
    tool_relations: dict[str, list[dict]]
    issues: list[EvidenceIssue]
    delegation_facts: list[dict] = field(default_factory=list)
    span_owners: dict = field(default_factory=dict)


@dataclass
class ExportResult:
    document: Any
    association: dict
    validation: dict
    manifest: dict
