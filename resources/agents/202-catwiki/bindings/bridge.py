"""Call the original RAG graph with its native PostgreSQL checkpointer."""
import asyncio
import runpy
from uuid import uuid4

def create_graph():
    runpy.run_path("/opt/agent/bootstrap/start.py")
    # Match native API startup: initialize the service facade before the graph.
    import app.services
    from langchain_openai import ChatOpenAI
    from langchain_core.messages import HumanMessage
    from app.core.ai.graph.logic import create_agent_graph
    from app.core.ai.graph.checkpointer import get_checkpointer, setup_checkpointer_tables, close_checkpointer_pool
    model=ChatOpenAI(model="gpt-4o-mini")
    class NativeRAG:
        async def ainvoke(self,inputs,config=None):
            text=inputs["message"]
            if not isinstance(text,str) or not text.strip():raise ValueError("Nonempty text required")
            try:
                await setup_checkpointer_tables()
                async with get_checkpointer() as cp:
                    graph=create_agent_graph(checkpointer=cp,model=model)
                    result=await graph.ainvoke({"messages":[HumanMessage(content=text)],"site_id":None,
                        "iteration_count":0,"consecutive_empty_count":0,"source_offset":0,"seen_tool_hashes":[]},
                        {"configurable":{"thread_id":uuid4().hex,"site_id":None,"tenant_id":None}})
                messages=result.get("messages",[])
                if not messages or messages[-1].type!="ai" or not messages[-1].content:
                    raise RuntimeError("Native RAG graph returned no assistant answer")
                return result
            finally:await close_checkpointer_pool()
        def invoke(self,inputs,config=None):return asyncio.run(self.ainvoke(inputs,config))
    return NativeRAG()
