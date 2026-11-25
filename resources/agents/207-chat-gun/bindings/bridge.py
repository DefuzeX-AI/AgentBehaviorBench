"""Send text through the native authenticated gateway to the complete MCP agent."""
import json
import os
import urllib.request
import uuid


class NativeBinding:
    def invoke(self, value, config=None):
        def post(path, payload):
            request = urllib.request.Request("http://127.0.0.1:8787/api/langgraph"+path,
                data=json.dumps(payload).encode(), method="POST", headers={
                    "Content-Type": "application/json", "X-Api-Key": os.environ["ABB_CHATGUN_TOKEN"],
                    "X-Idempotency-Key": uuid.uuid4().hex})
            with urllib.request.urlopen(request, timeout=300) as response:
                return json.load(response)
        thread = post("/threads", {})
        text = value.get("message", "") if isinstance(value, dict) else str(value)
        result = post("/threads/"+thread["thread_id"]+"/runs/wait", {
            "assistant_id": "mcp_agent", "input": {"messages": [{"role": "user", "content": text}]}})
        if result.get("__interrupt__") or result.get("error"):
            raise RuntimeError("Native Chat-Gun stopped: " + str(result.get("error") or result["__interrupt__"]))
        replies = [m for m in result.get("messages", []) if m.get("type", m.get("role")) in ("ai", "assistant") and m.get("content")]
        if not replies:
            raise RuntimeError("Native Chat-Gun returned no assistant reply")
        return result


def create_graph():
    import runpy
    runpy.run_path("/opt/agent/bootstrap/start.py", run_name="abb_deployment")
    return NativeBinding()
