"""ABB session/input adapter for DecompAI's unchanged native ReAct graph."""
from __future__ import annotations

import ast
import asyncio
import importlib
import json
import os
import struct
import sys
import uuid
from pathlib import Path

UNIT = Path(__file__).resolve().parents[1]
SOURCE = UNIT / "agent"


def parse_input(value):
    if isinstance(value, dict) and set(value) == {"request"}:
        value = value["request"]
    if isinstance(value, str):
        text = value.strip()
        if not text:
            raise ValueError("A binary-analysis request is required")
        try:
            decoded = json.loads(text)
        except json.JSONDecodeError:
            decoded = {"request": text}
        value = decoded if isinstance(decoded, dict) else {"request": text}
    if not isinstance(value, dict):
        raise ValueError("Input must be text or a JSON object")
    request = value.get("request") or value.get("instruction") or value.get("prompt")
    if not isinstance(request, str) or not request.strip():
        raise ValueError("Supply a nonempty request/instruction/prompt")
    binary = value.get("binary_path") or str(UNIT / "fixtures/branch")
    if not isinstance(binary, str):
        raise ValueError("binary_path must be a path string")
    binary = Path(binary).resolve()
    roots = [UNIT / "fixtures", Path(os.environ.get("ANALYSIS_SESSIONS_ROOT", "/tmp/decompai_analysis_sessions"))]
    if not any(binary.is_relative_to(p.resolve()) for p in roots):
        raise ValueError("binary_path must be in the deployed fixture or session directory")
    with binary.open("rb") as handle:
        header = handle.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[5] != 1:
        raise ValueError("A little-endian Linux ELF binary is required")
    if struct.unpack("<H", header[18:20])[0] not in (3, 62):
        raise ValueError("This deployment supports x86/i386 and x86-64 ELF only")
    return request.strip(), binary


def upstream_system_prompt():
    """Read the native UI's literal prompt without paraphrasing its behavior."""
    tree = ast.parse((SOURCE / "src/main.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "system_prompt" for t in node.targets):
            result = ast.literal_eval(node.value)
            if isinstance(result, str):
                return result
    raise RuntimeError("Pinned upstream session prompt was not found")


def _native():
    if sys.platform != "linux" or not Path("/opt/abb-runtime/agentbench").is_dir():
        raise RuntimeError("Native tool execution requires ABB's Linux Agent container")
    key = os.environ.get("OPENAI_API_KEY")
    if not key:
        raise RuntimeError("Runtime model interception credential is required")
    model_name = os.environ.get("ABB_AGENT_MODEL") or os.environ.get("LLM_MODEL") or "glm-5.3-flash"
    if model_name != "glm-5.3-flash":
        raise ValueError("This deployment is pinned to glm-5.3-flash")
    os.environ["LLM_MODEL"] = model_name
    os.environ["DECOMPAI_RUNNER_BUILD"] = "false"
    sys.path.insert(0, str(SOURCE))
    sys.path.insert(0, str(Path(__file__).parent))
    from container_transport import install
    utils = importlib.import_module("src.utils.utils")
    shell = importlib.import_module("src.tools.sandboxed_shell.dockerized_bash")
    install(utils, shell)
    # src.utils reexports function references. Refresh only the transport export.
    importlib.import_module("src.utils").run_command_in_docker = utils.run_command_in_docker
    native = importlib.import_module("src.main")
    # Retain the native ChatOpenAI object/tool bindings, while bounding retries/output.
    model = native.model.bound
    model.max_retries = 0
    model.max_tokens = int(os.environ.get("DECOMPAI_OUTPUT_LIMIT", "3072"))
    if "reasoning_effort" in type(model).model_fields:
        model.reasoning_effort = "low"
    else:
        model.model_kwargs = {**model.model_kwargs, "reasoning_effort": "low"}
    model.extra_body = {"thinking": {"type": "enabled"}}
    return native


class Workflow:
    async def ainvoke(self, value, config=None, **kwargs):
        request, binary = parse_input(value)
        native = _native()
        from langchain_core.messages import HumanMessage, SystemMessage
        from langchain_core.callbacks import BaseCallbackHandler

        class Budget(BaseCallbackHandler):
            raise_error = True
            def __init__(self):
                self.calls = 0
                self.exceeded = False
                self.truncated = False
            def on_chat_model_start(self, *args, **kwargs):
                self.calls += 1
                if self.calls > int(os.environ.get("DECOMPAI_MAX_CALLS", "8")):
                    self.exceeded = True
                    raise RuntimeError("Deployment model-call budget exhausted")
            def on_llm_end(self, response, **kwargs):
                for group in response.generations:
                    for generation in group:
                        reason = getattr(generation, "message", None)
                        metadata = getattr(reason, "response_metadata", {})
                        if metadata.get("finish_reason") in ("length", "max_tokens"):
                            self.truncated = True

        budget = Budget()
        cfg = dict(config or {})
        cfg["configurable"] = {**cfg.get("configurable", {}), "thread_id": uuid.uuid4().hex}
        cfg["recursion_limit"] = min(int(cfg.get("recursion_limit", 24)), 24)
        cfg["callbacks"] = [*(cfg.get("callbacks") or []), budget]
        session = native.utils.create_session_for_binary(str(binary))
        state = {"messages": [SystemMessage(content=upstream_system_prompt()), HumanMessage(content=request)],
                 "binary_path": str(Path(session) / binary.name), "session_path": session,
                 "disassembled_path": None, "model_name": "glm-5.3-flash",
                 "model_context_length": native.model_context_length,
                 "r2_stateful_shell_history": [], "r2_stateful_shell_output_line_count": 0}
        try:
            result = await native.graph.ainvoke(state, config=cfg, **kwargs)
            if budget.exceeded or budget.truncated:
                raise RuntimeError("Model budget exhausted or response truncated; no completed answer claimed")
            messages = result.get("messages", [])
            if not messages or getattr(messages[-1], "type", None) != "ai" or getattr(messages[-1], "tool_calls", []):
                raise RuntimeError("Native graph did not return a final assistant message")
            return {"answer": messages[-1].content, "messages": messages,
                    "session_path": session, "binary_path": state["binary_path"],
                    "model_calls": budget.calls}
        finally:
            from container_transport import close_all
            close_all()

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config=config, **kwargs))


def create_graph():
    return Workflow()
