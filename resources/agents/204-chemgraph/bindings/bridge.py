"""Use ChemGraph's native default workflow and public run method."""
import asyncio
import os
from pathlib import Path

def create_graph():
    workspace=Path.home()/"chemgraph-workspace"
    workspace.mkdir(exist_ok=True);os.chdir(workspace)
    from chemgraph.agent.llm_agent import ChemGraph
    agent=ChemGraph(model_name="gpt-4o-mini",api_key=os.environ["OPENAI_API_KEY"])
    class NativeChemGraph:
        async def ainvoke(self,inputs,config=None):
            text=inputs["message"]
            if not isinstance(text,str) or not text.strip():raise ValueError("Nonempty text required")
            answer=await agent.run(text)
            if not getattr(answer,"content",None):raise RuntimeError("Native ChemGraph produced no answer")
            return {"messages":[answer]}
        def invoke(self,inputs,config=None):return asyncio.run(self.ainvoke(inputs,config))
    return NativeChemGraph()
