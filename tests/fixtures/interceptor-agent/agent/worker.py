from __future__ import annotations

import json
import os
import urllib.request


payload = json.dumps(
    {
        "model": "smoke-model",
        "messages": [{"role": "user", "content": "hello"}],
    }
).encode("utf-8")
upstream = urllib.request.Request(
    os.environ["MODEL_URL"],
    data=payload,
    headers={
        "Authorization": f"Bearer {os.environ['MODEL_TOKEN']}",
        "Content-Type": "application/json",
    },
)
with urllib.request.urlopen(upstream, timeout=20) as response:
    body = json.loads(response.read())
assert body["json"]["model"] == "openrouter-smoke-model"
print("Model request completed successfully")
print("status: 200")
print("model: " + body["json"]["model"])
