"""One evidence-based execution ownership resolver."""
from copy import deepcopy
from agentbench.observe.tool_links import SCOPE_KEYS, compatible, resolve_tools
from .contracts import execution_key, ExecutionNode, ExecutionGraph, EvidenceIssue
from .adapters import selected


def resolve_hierarchy(bundle, *, adapters=()):
    key = execution_key(bundle, None, "runtime", "root")
    root = ExecutionNode(key, bundle.run.get("agent_id") or "unknown", status=bundle.run.get("status", "unknown"))
    nodes, links, issues = {key.id: root}, [], list(bundle.issues)
    facts = []
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
    boundaries = {n.boundary_id: n.key.id for n in nodes.values() if n.boundary_id}
    blocked_boundaries = set()
    bad = set()
    root_sessions = {(item.get("acp_summary") or {}).get("session", {}).get("sessionId")
                     for item in bundle.inputs}
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

    tools = {t["id"]: t for t in bundle.tools}
    accepted = []
    for link in links:
        tool = tools.get(link.tool_id)
        parent = owner(tool.get("span")) if tool else None
        if tool and tool.get("native_session_id") and tool["native_session_id"] not in root_sessions:
            parent = None
        if parent is None or parent == link.child_id or nodes[link.child_id].parent_id not in (None, parent):
            issues.append(EvidenceIssue("invalid_delegation", "No unambiguous parent execution", [link.child_id]))
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
        if record.get("native_session_id") and record["native_session_id"] not in root_sessions and owners[record["id"]] == key.id:
            owners[record["id"]] = None
        proposals = native_owners.get(record["id"], set())
        if proposals:
            existing = owners[record["id"]]
            proposals = proposals | ({existing} if existing else set())
            owners[record["id"]] = next(iter(proposals)) if len(proposals) == 1 and not record.get("identity_conflicts") else None
            if owners[record["id"]] is None:
                issues.append(EvidenceIssue("conflicting_native_ownership", "Native and framework ownership cannot be reconciled", [record["id"]]))
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
