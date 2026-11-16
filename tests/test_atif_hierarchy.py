from copy import deepcopy
from tests.atif_fixtures import child_bundle
from agentbench.trajectory.atif.hierarchy import resolve_hierarchy
import pytest


def test_same_name_children_and_reused_tool_id_are_isolated(tmp_path):
    bundle = child_bundle(tmp_path)
    graph = resolve_hierarchy(bundle, adapters=["deepagents"])
    assert len(graph.nodes) == 3
    assert len({graph.owners[m["id"]] for m in bundle.models}) == 2
    assert all(r["status"] == "exact" for values in graph.tool_relations.values() for r in values)


def test_attempt_identity_changes_ids_but_export_does_not_randomize(tmp_path):
    bundle = child_bundle(tmp_path)
    first = resolve_hierarchy(bundle, adapters=["deepagents"])
    assert first.root_id == resolve_hierarchy(bundle, adapters=["deepagents"]).root_id
    bundle.run["attempt_id"] = "another-attempt"
    second = resolve_hierarchy(bundle, adapters=["deepagents"])
    assert not set(first.nodes).intersection(second.nodes)


def test_unknown_tool_stays_candidate_not_removed_by_partitioning(tmp_path):
    bundle = child_bundle(tmp_path)
    tool = deepcopy(next(t for t in bundle.tools if t["tool_call_id"] == "reused-id"))
    tool.update(id="unassigned", span=None)
    bundle.tools.append(tool)
    graph = resolve_hierarchy(bundle, adapters=["deepagents"])
    assert graph.owners["unassigned"] is None
    assert all(r["status"] == "ambiguous" for values in graph.tool_relations.values() for r in values)


@pytest.mark.parametrize("failure", ["missing", "cycle", "identity"])
def test_broken_ancestry_never_defaults_to_root(tmp_path, failure):
    bundle = child_bundle(tmp_path)
    root = next(s for s in bundle.spans.values() if s["name"] == "graph")
    if failure == "identity":
        root["identity_conflicts"] = ["run_id"]
    else:
        root["parent"] = "absent" if failure == "missing" else root["id"]
    graph = resolve_hierarchy(bundle, adapters=["deepagents"])
    assert all(owner is None for owner in graph.owners.values())
    assert len(graph.nodes) == 1


def test_nested_child_uses_nearest_confirmed_boundary(tmp_path):
    bundle = child_bundle(tmp_path)
    child_one, child_two = [s for s in bundle.spans.values() if s["metadata"].get("lc_agent_name")]
    delegate_two = bundle.spans[child_two["parent"]]
    delegate_two["parent"] = child_one["id"]
    graph = resolve_hierarchy(bundle, adapters=["deepagents"])
    children = [n for n in graph.nodes.values() if n.parent_id]
    assert len(children) == 2
    assert sum(n.parent_id == graph.root_id for n in children) == 1


def test_conflicting_multiple_parents_are_not_published(tmp_path, monkeypatch):
    from agentbench.trajectory.atif.adapters.deepagents import DeepAgentsAdapter
    from agentbench.trajectory.atif.contracts import DelegationLink
    bundle = child_bundle(tmp_path)
    proposal = DeepAgentsAdapter().identify(bundle)
    proposal.links.append(DelegationLink(None, proposal.nodes[0].key.id, proposal.links[1].tool_id))
    class ConflictingAdapter:
        def identify(self, bundle):
            return proposal
    monkeypatch.setattr("agentbench.trajectory.atif.hierarchy.selected", lambda names: [ConflictingAdapter()])
    graph = resolve_hierarchy(bundle)
    assert proposal.nodes[0].key.id not in graph.nodes
    assert any(owner is None for owner in graph.owners.values())
