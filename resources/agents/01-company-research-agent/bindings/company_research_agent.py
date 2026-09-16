"""Minimal binding for the Company Research Agent LangGraph compiled graph.

This module exports a factory create_graph() that returns the native compiled graph
from langgraph_entry.py without input or output adaptation.

The upstream Graph class in backend/graph.py builds a multi-node async workflow
accepting input parameters like company (required), company_url, industry, hq_location, and job_id.
The run() method returns asynchronous state dict updates streaming through the
research pipeline.

The agent.toml adapter selects input_key='company' for text inputs mapped to the
company parameter. The compiled graph natively supports this and full mapping of
optional inputs.

No extra state or resources are managed by this binding.
"""


def create_graph():
    """Return the compiled LangGraph graph instance from langgraph_entry.py."""
    from langgraph_entry import graph
    return graph
