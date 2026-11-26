"""One evidence-based execution ownership resolver."""
from copy import deepcopy
from agentbench.observe.artifact_paths import SESSION_OUTPUT
from agentbench.observe.tool_links import SCOPE_KEYS, compatible, resolve_tools
from .contracts import execution_key, ExecutionNode, ExecutionGraph, EvidenceIssue
from .adapters import selected


def resolve_hierarchy(bundle, *, adapters=()):
    '''
    Resolve the execution hierarchy for a given evidence bundle.
    
    '''

    key = execution_key(bundle, None, "runtime", "root")
    root = ExecutionNode(key, bundle.run.get("agent_id") or "unknown", status=bundle.run.get("status", "unknown"))
    nodes, links, issues = {key.id: root}, [], list(bundle.issues)
    facts, continues = [], {}
    for adapter in selected(adapters):
        found = adapter.identify(bundle)
        for node in found.nodes:
            if node.key.id in nodes and nodes[node.key.id] != node:
                issues.append(EvidenceIssue("conflicting_boundary", "Conflicting execution boundary", [node.key.id]))
            else:
                nodes[node.key.id] = node
        links.extend(found.links)
        issues.extend(found.issues)
        facts.extend(found.facts)
        continues.update(found.same_execution)
    # A record an adapter found to continue another record's execution shares
    # that record's session, and with it the turn the session was reported in.
    recorded = {r["id"]: r for r in bundle.models + bundle.tools}
    for rid, anchor in continues.items():
        record, source = recorded.get(rid), recorded.get(anchor)
        if (record and source and source.get("native_session_id") and not record.get("native_session_id")
                and not record.get("identity_conflicts")):
            record["native_session_id"] = source["native_session_id"]
            record["session_evidence"] = list(source.get("session_evidence", []))
    boundaries = {n.boundary_id: n.key.id for n in nodes.values() if n.boundary_id}
    blocked_boundaries = set()
    bad = set()
    root_sessions = {(item.get("acp_summary") or {}).get("session", {}).get("sessionId")
                     for item in bundle.inputs}
    shared = bundle.auxiliary_artifacts.get(SESSION_OUTPUT + "/acp-summary.json") or {}
    root_sessions.add((shared.get("session") or {}).get("sessionId"))
    root_sessions.discard(None)

    def owner(span_id):
        path, cursor, nearest = set(), span_id, None
        while cursor:
            if cursor in path:
                bad.add(("cyclic_parent", span_id))
                return None
            path.add(cursor)
            if cursor in blocked_boundaries:
                return None
            span = bundle.spans.get(cursor)
            if span is None:
                bad.add(("missing_parent", span_id))
                return None
            if span.get("identity_conflicts"):
                bad.add(("identity_conflict", span_id))
                return None
            if nearest is None and cursor in boundaries:
                nearest = boundaries[cursor]
            parent = bundle.spans.get(span["parent"])
            if parent and not compatible(span, parent):
                bad.add(("parent_identity_conflict", span_id))
                return None
            cursor = span["parent"]
        return nearest or key.id

    def exported_root(record):
        """An Agent-exported step record has no ABB span to walk. The root owns it
        when it names a root session, or names none and no delegation was
        proposed. Where callbacks are the step record, an exported span that
        matched none stays unowned unless a delegation adapter claims it."""
        # The wire and ACP records such a source merges in have no span either.
        if (not bundle.exported_steps or record.get("span") or record.get("identity_conflicts")
                or record.get("source") not in ("agent_native", "auto_instrumented", "wire", "acp")):
            return False
        session = record.get("native_session_id")
        return session in root_sessions if session else not links

    tools = {t["id"]: t for t in bundle.tools}
    accepted = []
    for link in links:
        tool = tools.get(link.tool_id)
        parent = owner(tool["span"]) if tool and tool.get("span") and not tool.get("identity_conflicts") else None
        if tool and parent is None and exported_root(tool):
            parent = key.id
        # An exported spawn inside a child run has no span to walk either; the
        # adapter's parent stands only when that execution owns the tool.
        proposed = nodes.get(link.parent_id)
        if (tool and parent is None and bundle.exported_steps and not tool.get("span")
                and not tool.get("identity_conflicts") and proposed and tool["id"] in proposed.record_ids):
            parent = link.parent_id
        if tool and tool.get("native_session_id") and tool["native_session_id"] not in root_sessions:
            proposed = nodes.get(link.parent_id)
            # Nested native spawns share the framework root span. Accept a
            # different parent only when its session and owned tool both agree.
            if (parent == key.id and proposed and proposed.key.native_session_id == tool["native_session_id"]
                    and tool["id"] in proposed.record_ids):
                parent = proposed.key.id
            else:
                parent = None
        if link.parent_id and link.parent_id != parent:
            parent = None
        if parent is None or parent == link.child_id or nodes[link.child_id].parent_id not in (None, parent):
            issues.append(EvidenceIssue("invalid_delegation", "No unambiguous parent execution", [link.child_id]))
            if nodes[link.child_id].boundary_id:
                blocked_boundaries.add(nodes[link.child_id].boundary_id)
            continue
        link.parent_id = parent
        nodes[link.child_id].parent_id = parent
        accepted.append(link)
    # A proposed boundary needs exactly one delegation, and a path to the root.
    valid = {key.id}
    changed = True
    while changed:
        changed = False
        for nid, node in nodes.items():
            if nid in valid:
                continue
            incoming = [l for l in accepted if l.child_id == nid]
            if len(incoming) == 1 and node.parent_id in valid and node.boundary_id not in blocked_boundaries:
                valid.add(nid)
                changed = True
    for nid, node in nodes.items():
        if nid not in valid:
            if node.boundary_id:
                blocked_boundaries.add(node.boundary_id)
            issues.append(EvidenceIssue("unconfirmed_execution", "Execution has conflicting, cyclic or missing delegation", [nid]))
    accepted = [l for l in accepted if l.child_id in valid]
    native_owners = {}
    for nid, node in nodes.items():
        for rid in node.record_ids:
            native_owners.setdefault(rid, set()).add(nid if nid in valid else None)
    # Ownership walks validate complete ancestry, including ancestors above a
    # recognized child boundary, rather than accepting disconnected fragments.
    owners = {}
    for record in bundle.models + bundle.tools:
        owners[record["id"]] = None if record.get("identity_conflicts") else owner(record["span"]) if record.get("span") else None
        if exported_root(record):
            owners[record["id"]] = key.id
        if record.get("native_session_id") and record["native_session_id"] not in root_sessions and owners[record["id"]] == key.id:
            owners[record["id"]] = None
        proposals = native_owners.get(record["id"], set())
        if proposals:
            existing = owners[record["id"]]
            proposals = proposals | ({existing} if existing else set())
            owners[record["id"]] = next(iter(proposals)) if len(proposals) == 1 and not record.get("identity_conflicts") else None
            if owners[record["id"]] is None:
                issues.append(EvidenceIssue("conflicting_native_ownership", "Native and framework ownership cannot be reconciled", [record["id"]]))
    # Without a session to share, the continuing record follows the owner directly.
    for rid, anchor in continues.items():
        if rid in owners and owners[rid] is None and owners.get(anchor) and not recorded[rid].get("identity_conflicts"):
            owners[rid] = owners[anchor]
    # A model call only the wire recorded names no execution. It ran where the
    # tool calls it emitted were executed, when they all ran in one execution.
    if bundle.exported_steps:
        executed = {}
        for tool in bundle.tools:
            if tool.get("tool_call_id"):
                executed.setdefault(tool["tool_call_id"], set()).add(owners[tool["id"]])
        for model in bundle.models:
            if owners[model["id"]] is not None or model.get("source") != "wire" or model.get("identity_conflicts"):
                continue
            output = model.get("client_output") or model["output"]
            ran_in = set().union(*(executed.get(call.get("id"), set()) for call in output.get("tool_calls") or []))
            if len(ran_in) == 1 and None not in ran_in:
                owners[model["id"]] = ran_in.pop()
    nodes = {nid: node for nid, node in nodes.items() if nid in valid}
    for code, sid in sorted(bad):
        issues.append(EvidenceIssue(code, "Framework ancestry cannot be verified", [sid]))
    for identifier, execution in owners.items():
        if execution is None:
            issues.append(EvidenceIssue("unassigned_record", "Execution ownership is unknown", [identifier]))
    model_rows = []
    for model in bundle.models:
        output = model.get("client_output") or model.get("framework_output") or model["output"]
        calls = output.get("tool_calls") or model["output"].get("tool_calls") or []
        model_rows.append({**deepcopy(model), "execution_id": owners[model["id"]],
                           "emitted_tool_ids": [c["id"] for c in calls if c.get("id")]})
    tool_rows = [{**t, "execution_id": owners[t["id"]]} for t in bundle.tools]
    relations = resolve_tools(model_rows, tool_rows, scope_keys=(*SCOPE_KEYS, "execution_id"))
    for mid, values in relations.items():
        for value in values:
            if value["status"] != "exact":
                issues.append(EvidenceIssue("tool_" + value["status"], "Tool association is not exact", [mid, value["tool_call_id"]]))
    span_owners = {sid: owner(sid) for sid in bundle.spans}
    return ExecutionGraph(key.id, nodes, owners, accepted, relations, issues, facts, span_owners)
