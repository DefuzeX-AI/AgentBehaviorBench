# Example 01: forward to an existing compatible compiled graph

Source reference: `resources/agents/10-data-enrichment/agent/langgraph.json`.
That file exports `./src/enrichment_agent/graph.py:graph` under graph ID `agent`.
When native input/output are already suitable, the generated integration still
selects a binding. The relevant generated configuration is:

```toml
[adapter]
type = "langgraph"
mode = "in_process"
config = "langgraph.json"
graph_id = "agent"
binding = "bridge.py:create_graph"
```

BBA calls the forwarding factory below, which returns the actual upstream graph.
There is no need for a wrapper class or duplicated workflow. This is a COMPLETE
`bindings/bridge.py` under the stated package assumption:

```python
"""Expose the upstream compiled graph without changing its inputs or outputs.

Prerequisite: Docker installs the upstream enrichment_agent package.
The returned graph owns invoke/ainvoke; this module creates no external resources.
"""


def create_graph():
    """Accept no arguments and return the native compiled graph.

    Its structured input includes topic and extraction_schema. Inputs and native
    state outputs are forwarded unchanged by BBA; no history is constructed here.
    This returns the upstream module's existing object, not a fresh private graph.
    No adapter-specific input/output conversion is needed for this graph.
    """
    from enrichment_agent.graph import graph

    return graph
```

This import is specific to data-enrichment. For another repository, confirm its
package installation and exported symbol from supplied files. Merely placing
source under `agent/` does not install a Python package. BBA's binding loader adds
the binding import root temporarily; it does not install upstream dependencies.
