"""Initialize the real upstream graph and retrieval stack without calling an LLM.

Run in the staged ABB image with ``docker run --rm --network none IMAGE python
/opt/agent/bindings/offline_check.py``. This is NOT Local Smoke, a Judge report,
or a behavioral evaluation. No graph/model invoke or RAG summarization is used.
"""
from __future__ import annotations

import json
import os


def main() -> None:
    # Construction of ChatOpenAI requires a value, but this diagnostic never
    # invokes it. Do not use a real host credential for offline initialization.
    os.environ["OPENAI_API_KEY"] = "abb-offline-initialization-only"
    os.environ["HF_HUB_OFFLINE"] = "1"
    os.environ["TRANSFORMERS_OFFLINE"] = "1"

    from bridge import create_graph
    from langgraph.graph.state import CompiledStateGraph

    graph = create_graph()
    try:
        native = graph._load()
        assert isinstance(native.agent, CompiledStateGraph), type(native.agent).__name__
        from agent.tools import agent_tools

        names = (
            "rag_summarize", "get_weather", "get_user_location", "get_user_id",
            "get_current_month", "fetch_external_data", "fill_context_for_report",
        )
        assert all(getattr(agent_tools, name).name == name for name in names)
        documents = agent_tools.rag.retriever_docs("\u6ee4\u7f51\u7ef4\u62a4")
        assert documents and all(doc.page_content.strip() for doc in documents)
        record = agent_tools.fetch_external_data.invoke({"user_id": "1001", "month": "2025-01"})
        assert isinstance(record, dict) and record
        count = len(agent_tools.rag.vector_store.vector_store.get()["ids"])
        print(json.dumps({
            "check": "offline-initialization-only",
            "native_graph_type": type(native.agent).__name__,
            "native_tools": names,
            "indexed_chunks": count,
            "retrieved_documents": len(documents),
            "sample_ledger_read": True,
            "model_invocations": 0,
            "behavioral_evaluation": "NOT RUN",
            "local_smoke": "NOT RUN",
        }, sort_keys=True))
    finally:
        graph.close()


if __name__ == "__main__":
    main()
