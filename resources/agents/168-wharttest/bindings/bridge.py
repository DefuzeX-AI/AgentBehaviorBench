"""Call the native authenticated Agent Loop API and retain its full response."""
import asyncio
import json


class NativeBinding:
    def __init__(self, deployment):
        self.deployment = deployment

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        import httpx
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        try:
            async with httpx.AsyncClient(timeout=300, trust_env=False) as client:
                response = await client.post("http://127.0.0.1:8000/api/orchestrator/agent-loop/",
                    headers={"Authorization": "Bearer " + self.deployment["token"]},
                    json={"message": text, "project_id": self.deployment["project_id"], "stream": False})
                result = response.json()
                if response.is_error or result.get("status") != "success":
                    raise RuntimeError(json.dumps(result, ensure_ascii=False))
                return result
        finally:
            for process in self.deployment["processes"]:
                process.terminate()
            for process in self.deployment["processes"]:
                try:
                    process.wait(timeout=10)
                except Exception:
                    process.kill()


def create_graph():
    import runpy
    from concurrent.futures import ThreadPoolExecutor
    # Django's synchronous setup/ORM must not run on the adapter's event loop.
    with ThreadPoolExecutor(max_workers=1) as executor:
        state = executor.submit(runpy.run_path, "/opt/agent/bootstrap/start.py",
                                run_name="abb_deployment").result()
    return NativeBinding(state["deployment"])
