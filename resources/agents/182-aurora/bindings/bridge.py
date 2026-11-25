"""Authenticate through native NextAuth, then use Aurora's native chat WebSocket."""
import asyncio
import json
import runpy
import secrets
import uuid
from urllib.parse import quote


class NativeAurora:
    def __init__(self, processes, diagnostics):
        self.processes = processes
        self.diagnostics = diagnostics

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        import httpx
        import websockets
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        password = secrets.token_urlsafe(24)
        email = "abb-local@example.com"
        try:
            async with httpx.AsyncClient(trust_env=False, timeout=60, follow_redirects=True) as client:
                response = await client.post("http://127.0.0.1:5080/api/auth/register",
                    json={"email": email, "password": password, "name": "ABB local user", "org_name": "ABB Local"})
                response.raise_for_status()
                csrf = await client.get("http://127.0.0.1:3000/api/auth/csrf")
                csrf.raise_for_status()
                response = await client.post("http://127.0.0.1:3000/api/auth/callback/credentials",
                    data={"csrfToken": csrf.json()["csrfToken"], "email": email, "password": password,
                          "callbackUrl": "http://127.0.0.1:3000", "json": "true"})
                response.raise_for_status()
                session = await client.get("http://127.0.0.1:3000/api/auth/session")
                session.raise_for_status()
                user_id = session.json().get("userId")
                if not user_id:
                    raise RuntimeError("Native Aurora login did not establish a user session")
                token = await client.get("http://127.0.0.1:3000/api/ws-token")
                token.raise_for_status()
                url = "ws://127.0.0.1:5006?token="+quote(token.json()["token"])
            async with websockets.connect(url, open_timeout=30, max_size=16*1024*1024) as ws:
                session_id = uuid.uuid4().hex
                ready = json.loads(await asyncio.wait_for(ws.recv(), 60))
                if ready.get("type") == "error":
                    raise RuntimeError(json.dumps(ready))
                await ws.send(json.dumps({"type": "init", "user_id": user_id, "session_id": session_id}))
                await ws.send(json.dumps({"query": text, "user_id": user_id, "session_id": session_id,
                    "model": "openai/gpt-4o-mini", "mode": "agent"}))
                events = []
                reply = []
                while True:
                    event = json.loads(await asyncio.wait_for(ws.recv(), 300))
                    events.append(event)
                    if event.get("type") == "error":
                        raise RuntimeError(json.dumps(event, ensure_ascii=False))
                    if event.get("type") == "message":
                        content = event.get("data", {}).get("text")
                        if isinstance(content, str):
                            reply.append(content)
                    if event.get("type") == "status" and event.get("data", {}).get("status") == "END":
                        if not ''.join(reply).strip():
                            raise RuntimeError("Native Aurora ended without an assistant reply")
                        return {"reply": ''.join(reply), "native_events": events}
        except Exception as error:
            diagnostic_secrets = [password]
            if "client" in locals():
                diagnostic_secrets.extend(cookie.value for cookie in client.cookies.jar)
            raise self.diagnostics("Native Aurora request failed: " + type(error).__name__, diagnostic_secrets) from error
        finally:
            for process in reversed(self.processes):
                if process.poll() is None:
                    process.terminate()


def create_graph():
    deploy = runpy.run_path("/opt/agent/bootstrap/start.py")
    return NativeAurora(*deploy["start_deployment"]())
