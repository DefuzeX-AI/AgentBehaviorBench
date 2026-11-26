"""Use the complete native document-analysis coordinator and its durable checkpoint."""
import asyncio
import json
import os
from pathlib import Path
import sys
from uuid import uuid4
sys.path.insert(0,"/app")

def create_graph():
    os.chdir("/app")
    os.environ.update(DOCMIND_LLM_BACKEND="openai_compatible",
        DOCMIND_LLM_REQUEST__MODEL="gpt-4o-mini",DOCMIND_OPENAI__API_KEY=os.environ["OPENAI_API_KEY"],
        DOCMIND_OPENAI__BASE_URL="https://api.openai.com/v1",
        DOCMIND_SECURITY__ENDPOINT_ALLOWLIST=json.dumps(["http://localhost","http://127.0.0.1","https://localhost","https://127.0.0.1","https://api.openai.com"]))
    from src.agents.coordinator import MultiAgentCoordinator
    class NativeDocMind:
        def invoke(self,inputs,config=None):
            text=inputs["message"]
            if not isinstance(text,str) or not text.strip():raise ValueError("Nonempty text required")
            coordinator=MultiAgentCoordinator(checkpointer_path=Path("/app/data/abb-checkpoints.sqlite"))
            try:
                result=coordinator.process_query(query=text,thread_id=uuid4().hex)
                reason=result.metadata.get("reason")
                if reason in {"initialization_failed","execution_failed","timeout","workflow_stopped"} or any(result.optimization_metrics.get(k) for k in ("error","timeout","stopped")):
                    raise RuntimeError("Native coordinator did not complete: "+str(reason))
                if not result.content:raise RuntimeError("Native coordinator returned no content")
                return result.model_dump(mode="json")
            finally:coordinator.close()
        async def ainvoke(self,inputs,config=None):return await asyncio.to_thread(self.invoke,inputs,config)
    return NativeDocMind()
