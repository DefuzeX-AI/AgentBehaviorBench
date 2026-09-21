"""Binding module exposing the Folder Mover LangGraph agent's compiled graph.

This module provides a synchronous factory create_graph() without arguments,
returning the native FolderMoverAgent instance defined in agent/folder_mover.py.
The FolderMoverAgent encapsulates a LangGraph StateGraph managing conversational
turns and calls to the move_folder tool.

Input to the graph is expected as a Mapping with key 'messages'. The declared
binding input_key='message' in the adapter configuration permits a string input
from BBA to be wrapped automatically. Output is the native LangGraph result.

invoke and ainvoke methods are supported to align with synchronous and asynchronous
callers. Resource lifecycle including model client closure is managed by the native
agent, including close() and aclose() methods.

No conversion or adaptation of the input/output beyond forwarding is needed.

Usage example:
    graph = create_graph()
    result = graph.invoke("Move folder from C:/src to D:/dest")  # sync
    # or asynchronously
    # result = await graph.ainvoke({"message": "Move folder from C:/src to D:/dest"})
    print(result["response"])

"""


def create_graph():
    """Return a fresh FolderMoverAgent instance which is the compiled LangGraph graph.

    This factory accepts no arguments. The returned graph supports invoke(value, config)
    and ainvoke(value, config) where value is a Mapping with key 'messages' or a string
    wrapped as {'message': string} by the adapter input_key.

    Returns:
        FolderMoverAgent: The native agent with invoke and ainvoke methods.
    """
    from folder_mover import create_graph as native_create_graph
    return native_create_graph()
