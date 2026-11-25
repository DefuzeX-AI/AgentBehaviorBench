"""Use native authenticated admission, embedded worker and persisted run result."""
import asyncio
import os
import runpy
import sys
from uuid import uuid4

def create_graph():
    runpy.run_path("/opt/agent/bootstrap/start.py")
    import httpx
    import uvicorn
    from agent_platform.applications.customer_service.main import app
    class NativeService:
        async def ainvoke(self, inputs, config=None):
            text=inputs["message"]
            if not isinstance(text,str) or not text.strip():
                raise ValueError("Expected nonempty text")
            server=uvicorn.Server(uvicorn.Config(app,host="127.0.0.1",port=8000,log_level="warning"))
            task=asyncio.create_task(server.serve())
            headers={"Authorization":"Bearer "+os.environ["AGENT_API_TOKEN"]}
            try:
                async with httpx.AsyncClient(base_url="http://127.0.0.1:8000",headers=headers,timeout=30,trust_env=False) as client:
                    for _ in range(180):
                        if task.done():
                            await task
                            raise RuntimeError("Native service exited before readiness")
                        try:
                            ready=await client.get("/api/v1/ready")
                            if ready.status_code==200: break
                        except httpx.ConnectError: pass
                        await asyncio.sleep(1)
                    else: raise TimeoutError("Native service readiness timed out")
                    response=await client.post("/api/v1/runs",json={"conversation_id":uuid4().hex,"message":text})
                    response.raise_for_status()
                    run=response.json()
                    for _ in range(180):
                        response=await client.get("/api/v1/runs/"+run["id"])
                        response.raise_for_status();run=response.json()
                        if run["status"] in {"completed","failed","cancelled"}: break
                        await asyncio.sleep(1)
                    else:
                        await client.post("/api/v1/runs/"+run["id"]+"/cancel")
                        raise TimeoutError("Native run did not finish")
                    if run["status"]!="completed" or not run.get("output"):
                        raise RuntimeError("Native run failed: "+str(run.get("error_code")))
                    return run["output"]
            finally:
                server.should_exit=True
                await task
        def invoke(self,inputs,config=None):
            return asyncio.run(self.ainvoke(inputs,config))
    return NativeService()
