"""Transport ABB inputs to the published StructureClaw LangGraph service."""
from __future__ import annotations

import json
import os
from pathlib import Path
import signal
import subprocess
import tempfile
import uuid


class StructureClawGraph:
    def __init__(self):
        self.root = Path(__file__).resolve().parents[1]
        self.conversation_id = str(uuid.uuid4())
        self.process = None
        self.pending = set()

    def invoke(self, value, config=None):
        if isinstance(value, str):
            value = {"message": value}
        if not isinstance(value, dict) or not isinstance(value.get("message"), str) or not value["message"].strip():
            raise ValueError("StructureClaw requires a nonempty message")
        request = dict(value)
        configurable = (config or {}).get("configurable", {})
        request.setdefault("conversationId", configurable.get("thread_id") or self.conversation_id)
        env = os.environ.copy()
        package = self.root / "agent/node_modules/@structureclaw/structureclaw"
        with tempfile.TemporaryDirectory(prefix="abb-structureclaw-") as temporary:
            result_file = Path(temporary) / "result.json"
            self.process = subprocess.Popen(
                ["node", str(self.root / "bindings/native.mjs"), str(result_file)],
                cwd=package, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE, text=True, start_new_session=True,
            )
            try:
                stdout, stderr = self.process.communicate(json.dumps({"input": request, "resume": request["conversationId"] in self.pending}), timeout=590)
                if self.process.returncode:
                    detail = stderr[-6000:]
                    for key, secret in env.items():
                        if any(term in key for term in ("KEY", "TOKEN", "SECRET")) and secret:
                            detail = detail.replace(secret, "[REDACTED]")
                    raise RuntimeError(f"StructureClaw exited {self.process.returncode}: {detail}")
                result = json.loads(result_file.read_text())
                if result.get("interrupts"):
                    self.pending.add(request["conversationId"])
                else:
                    self.pending.discard(request["conversationId"])
                return result
            except subprocess.TimeoutExpired:
                self.close()
                raise TimeoutError("StructureClaw exceeded its 590 second invocation limit") from None
            finally:
                self.close()

    def close(self):
        process, self.process = self.process, None
        if process is not None and process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL)
            process.communicate()


def create_graph():
    return StructureClawGraph()
