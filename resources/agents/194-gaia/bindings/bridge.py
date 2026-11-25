"""Use native local signup, conversation submission and durable reply polling."""
import asyncio
import json
import runpy
import secrets
import time
import uuid


class NativeGaia:
    def __init__(self, processes):
        self.processes = processes

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        import httpx
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        try:
            async with httpx.AsyncClient(base_url="http://127.0.0.1:8000/api/v1", trust_env=False, timeout=45) as client:
                response = await client.post("/auth/signup", json={"email": "abb-local@example.com",
                    "password": secrets.token_urlsafe(24), "name": "ABB local user"})
                response.raise_for_status()
                conversation = uuid.uuid4().hex
                response = await client.post("/conversations", json={"conversation_id": conversation, "source": "web"})
                response.raise_for_status()
                response = await client.post(f"/conversations/{conversation}/messages",
                    json={"message_id": uuid.uuid4().hex, "text": text})
                response.raise_for_status()
                deadline = time.monotonic()+420
                while time.monotonic() < deadline:
                    response = await client.get(f"/conversations/{conversation}")
                    response.raise_for_status()
                    state = response.json()
                    for item in state.get("items", []):
                        if item.get("kind") == "reply" and item.get("outcome"):
                            if item["outcome"] == "answered" and any(item.get("bubbles", [])):
                                return state
                            if item["outcome"] in ("failed", "stopped"):
                                raise RuntimeError(json.dumps(item, ensure_ascii=False))
                    if any(work.get("awaiting_approval") for work in state.get("state", {}).get("work", [])):
                        raise RuntimeError("Native GAIA requires human approval; no approval was supplied")
                    await asyncio.sleep(1)
                raise RuntimeError("Native GAIA produced no completed reply before the deadline")
        finally:
            for process in reversed(self.processes):
                if process.poll() is None:
                    process.terminate()


def create_graph():
    deploy = runpy.run_path("/opt/agent/bootstrap/start.py")
    return NativeGaia(deploy["start_deployment"]())
