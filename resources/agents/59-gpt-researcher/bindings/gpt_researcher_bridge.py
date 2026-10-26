"""Bridge the BBA text Case input to GPT Researcher's native multi-agent workflow.

Native entrypoint
-----------------
The upstream LangGraph application is registered in ``langgraph.json`` as graph
id ``agent`` at ``./multi_agents/agent.py:graph``.  That module compiles a demo
``ChiefEditorAgent`` at import time with a hardcoded question, so the exported
object is not a usable target for a per-Case text query.  This binding instead
runs the verified public lifecycle that module wraps: construct
``multi_agents.agents.ChiefEditorAgent(task, websocket=None,
stream_output=None)``, call ``init_research_team().compile()``, and invoke the
compiled native graph with ``ainvoke({'task': task}, config=config)`` (the same
call shape as the upstream ``run_research_task``; ``ainvoke``, not
``astream``).  The publisher node returns the final deliverable under the
native state key ``report``.

Adaptations
-----------
* The official Case boundary is TEXT only, and the manifest sets
  ``input_key = "query"``: BBA wraps scalar text as ``{'query': '<text>'}``
  before this binding runs.
* The wrapper node builds the complete native task dict: the query text plus
  the preserved upstream defaults (``max_sections 3``, ``max_plan_revisions
  3``, ``publish_formats {'markdown': True, 'pdf': True, 'docx': True}``,
  ``include_human_feedback False``, ``follow_guidelines False``, inert empty
  ``guidelines``, ``model 'gpt-4o'``, ``verbose False``).  ``publish_formats``
  is mandatory: the publisher node reads it unguarded and the inline template
  in ``multi_agents/agent.py`` omits it, which would crash the final node.
* ``include_human_feedback`` stays False so the human review node routes
  straight into parallel research instead of interrupting the run.
* The incoming ``config`` (LangChain RunnableConfig) is forwarded unchanged to
  the native graph so callbacks, tags, metadata and thread settings survive.
* The wrapper returns its complete state ``{'query': ..., 'report': ...}``;
  the manifest declares no ``output_key``.  A missing ``report`` key raises
  and fails the run; no answer text is ever manufactured here.

Concrete input (shape only)::

    {"query": "What are the latest advances in solid-state batteries?"}

Concrete output (shape only; the report text is the native publisher output)::

    {"query": "What are the latest advances in solid-state batteries?",
     "report": "<native research report markdown produced by the publisher node>"}

Prerequisites and ownership: the image installs the upstream source per
``langgraph.json`` (Python 3.12, dependency ``./multi_agents``), so
``multi_agents.agents`` is importable.  Provider and retriever credentials are
deployment concerns supplied under environment variable names
(``OPENAI_API_KEY`` via model interception, ``TAVILY_API_KEY``); no secret
value appears in this file.  The binding owns no long-lived resources: the
native agent, its compiled graph and its ``./outputs/run_...`` report files
are created and managed by native code per invocation, so there is nothing
for ``close()`` to release.
"""

from typing import TypedDict

from langchain_core.runnables.config import RunnableConfig

# Native defaults preserved from the upstream task template (multi_agents
# task.json / the inline template in multi_agents/agent.py).  follow_guidelines
# is False, so guidelines stays empty and inert; include_human_feedback is
# False so the human review node routes straight to research instead of
# interrupting the run.
_TASK_DEFAULTS = {
    "max_sections": 3,
    "max_plan_revisions": 3,
    "publish_formats": {"markdown": True, "pdf": True, "docx": True},
    "include_human_feedback": False,
    "follow_guidelines": False,
    "guidelines": [],
    "model": "gpt-4o",
    "verbose": False,
}


class BridgeState(TypedDict, total=False):
    """Wrapper state: the Case text arrives as ``query``; the node adds ``report``."""

    query: str
    report: str


def _task_from_query(query: str) -> dict:
    """Build the complete native task dict for one query.

    The publisher node requires ``publish_formats``; it is always included so
    the final node cannot crash on the template's omitted key.  No other task
    value is inferred from prior conversations or previous runs.
    """
    task = dict(_TASK_DEFAULTS)
    task["query"] = query
    return task


async def run_research(state: BridgeState, config: RunnableConfig) -> dict:
    """Run one full native research task for the current query only.

    Args:
        state: ``{'query': '<research request text>'}``.  Extra fields are
            rejected rather than silently dropped; no history, memory or
            missing business argument is synthesized.
        config: LangChain RunnableConfig forwarded unchanged to the native
            graph, preserving real framework observation callbacks.
    Returns:
        ``{'report': <native report state key>}`` as a node update; the
        compiled wrapper therefore finishes with ``query`` and ``report``.
    Raises:
        ValueError: if the wrapper input is not exactly one non-empty
            ``query`` string field.
        KeyError: if the native final state carries no ``report`` key.
        Any native execution error propagates unchanged as a failure.
    """
    if not isinstance(state, dict):
        raise ValueError("GPT Researcher expects a {'query': text} mapping")
    unexpected = set(state) - {"query"}
    if unexpected:
        raise ValueError(
            "GPT Researcher accepts exactly one field 'query'; "
            f"unsupported fields: {', '.join(sorted(unexpected))}"
        )
    query = state.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ValueError("Supply a non-empty research request as the 'query' field")

    task = _task_from_query(query)
    from multi_agents.agents import ChiefEditorAgent

    chief_editor = ChiefEditorAgent(task, websocket=None, stream_output=None)
    native_graph = chief_editor.init_research_team().compile()
    result = await native_graph.ainvoke({"task": task}, config=config)
    return {"report": result["report"]}


def create_graph():
    """Return the compiled wrapper graph; synchronous zero-argument factory.

    The wrapper has the single node ``run_research`` and exposes the standard
    compiled-graph ``invoke``/``ainvoke`` pair.  Every invocation constructs a
    fresh native ``ChiefEditorAgent``, so the returned object holds no mutable
    state and owns no external resources.  BBA wraps the text Case input as
    ``{'query': ...}`` per the manifest's ``input_key`` before calling it.
    """
    from langgraph.graph import END, StateGraph

    workflow = StateGraph(BridgeState)
    workflow.add_node("research_task", run_research)
    workflow.set_entry_point("research_task")
    workflow.add_edge("research_task", END)
    return workflow.compile()
