"""Shared LangGraph import helpers.

LangGraph is imported lazily so the legacy API service can still boot in
environments where dependencies have not been installed yet. Task files import
`import_langgraph` when they need to compile their own graph.
"""

from app.core.responses import AppError


def import_langgraph():
    """Import LangGraph primitives and return a clear setup error if missing."""

    try:
        from langgraph.graph import END, START, StateGraph
    except ImportError as exc:
        raise AppError("LangGraph\u672a\u5b89\u88c5\uff0c\u8bf7\u5148\u6267\u884c pip install -r requirements.txt") from exc
    return START, END, StateGraph
