"""ABB binding for EYamanS/texel-studio.

Native contract (source under ``agent/`` is unchanged):

1. **Entrypoint.** ``server.py`` is a FastAPI app; the job that paints a sprite,
   ``jobs/sprite_generate.SpriteGenerateHandler.run``, calls
   ``agent.run_agent_stream(gen_id, message, palette, size, model_name,
   style_prompt, sprite_type, reference_b64, on_step, ...)``. That function
   builds a ``Canvas``, the canvas tools and a LangGraph ``create_react_agent``,
   streams it until the model calls ``finish`` (or 80 messages), and returns the
   ``Canvas``. The binding calls that same function; ``server.py``, the job
   dispatcher, the Next.js frontend and ``worker.py`` are not started.

2. **Business inputs.** ``GenerateRequest`` in ``server.py`` carries ``prompt``,
   ``colors``, ``size``, ``system_prompt`` and ``sprite_type``. A text Case input
   is the ``prompt``; a JSON object with those field names is also accepted.
   Omitted fields take upstream values: ``size`` 16 (``GenerateRequest``),
   ``system_prompt`` ``DEFAULT_SYSTEM_PROMPT`` and ``colors`` the seeded
   "Default Earth" palette (``server.init_db``). ``sprite_type`` defaults to
   ``freeform``, the upstream type whose hint lets the model decide between an
   object on transparency and a filled scene; the API default ``block`` would
   force every arbitrary request into a seamless tile. These constants are read
   from ``server.py`` with ``ast`` so the module (Gemini client, SQLite schema)
   is never executed.

3. **Sessions.** Within one Case a later input is an edit of the same sprite,
   exactly like ``jobs/sprite_chat``: the same ``gen_id`` (so the same LangGraph
   thread in the native ``MemorySaver``) plus the current pixels as
   ``existing_pixels``. ``gen_id`` comes from ABB's stable Case thread ID.

4. **Execution configuration.** ``run_agent_stream`` has no ``config``
   parameter and passes its own ``{"configurable": {"thread_id": ...}}`` to
   ``agent.stream``. The binding applies ABB's config with LangChain's
   ``set_config_context`` so callbacks and tags reach the native graph.

5. **Model.** ``_get_llm`` sends any ``gpt-*`` model name to ``ChatOpenAI``
   with the default ``api.openai.com`` endpoint when ``OPENAI_BASE_URL`` is
   unset; that is the route declared in ``agent.toml``. ``gpt-4o-mini`` is one
   of upstream's listed ``OPENAI_MODELS``; ABB's interception rewrites the
   request to the configured run model and supplies the credential. As for any
   non-Ollama model, upstream treats it as vision-capable: the full toolset is
   exposed and ``view_canvas`` appends a base64 PNG preview as text.

6. **Not exercised.** Reference images (``reference_b64`` stays ``None``; the
   reference-generation job calls Gemini image models directly), photo
   conversion, tilesets, palette storage, S3/Redis (``REDIS_URL`` unset keeps
   the native ``MemorySaver``) and PNG export.

Output: ``{"answer": <report>}`` built from the returned ``Canvas`` -- the
upstream ``to_visual_grid`` rendering, palette legend, fill statistics and the
step log the native ``on_step`` callback emitted. Native exceptions propagate.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
import uuid
from collections.abc import Mapping
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"

MODEL_NAME = "gpt-4o-mini"
DEFAULT_SIZE = 16
DEFAULT_SPRITE_TYPE = "freeform"
ALLOWED_FIELDS = {"prompt", "colors", "size", "system_prompt", "sprite_type"}
STEP_LOG_LIMIT = 60


def _server_constants() -> tuple[str, list[str], set[str]]:
    """Read DEFAULT_SYSTEM_PROMPT, the seeded palette and sprite types from server.py."""
    tree = ast.parse((SOURCE_ROOT / "server.py").read_text(encoding="utf-8"))
    system_prompt = None
    sprite_types: set[str] = set()
    palette = None
    for node in tree.body:
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == "DEFAULT_SYSTEM_PROMPT":
                system_prompt = ast.literal_eval(node.value)
            elif name == "SPRITE_TYPES":
                sprite_types = set(ast.literal_eval(node.value))
        elif isinstance(node, ast.FunctionDef) and node.name == "init_db":
            for inner in ast.walk(node):
                if isinstance(inner, ast.List) and inner.elts and all(
                    isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value.startswith("#")
                    for e in inner.elts
                ):
                    palette = [e.value for e in inner.elts]
                    break
    if not system_prompt or not palette or not sprite_types:
        raise RuntimeError("server.py no longer defines the expected Texel Studio defaults")
    return system_prompt, palette, sprite_types


def _load_native_agent():
    """Import upstream ``agent.py`` under its own module name, as the jobs do."""
    if "agent" in sys.modules and getattr(sys.modules["agent"], "__file__", None) == str(SOURCE_ROOT / "agent.py"):
        return sys.modules["agent"]
    spec = importlib.util.spec_from_file_location("agent", SOURCE_ROOT / "agent.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["agent"] = module
    try:
        spec.loader.exec_module(module)
    except BaseException:
        sys.modules.pop("agent", None)
        raise
    return module


def _parse_input(value: Any, sprite_types: set[str]) -> dict[str, Any]:
    if isinstance(value, Mapping):
        fields = dict(value)
        if set(fields) == {"message"}:
            value = fields["message"]
        else:
            return _validate_fields(fields, sprite_types)
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case input must be a non-empty sprite request or a JSON object with 'prompt'")
    text = value.strip()
    if text.startswith("{"):
        try:
            loaded = json.loads(text)
        except json.JSONDecodeError:
            loaded = None
        if isinstance(loaded, dict) and "prompt" in loaded:
            return _validate_fields(loaded, sprite_types)
    return {"prompt": text}


def _validate_fields(fields: dict[str, Any], sprite_types: set[str]) -> dict[str, Any]:
    unknown = set(fields) - ALLOWED_FIELDS
    if unknown:
        raise ValueError(f"Unsupported fields: {sorted(unknown)}; accepted: {sorted(ALLOWED_FIELDS)}")
    prompt = fields.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError("'prompt' must be a non-empty string")
    if "size" in fields and (not isinstance(fields["size"], int) or isinstance(fields["size"], bool) or fields["size"] < 1):
        raise ValueError("'size' must be a positive integer")
    if "colors" in fields and (
        not isinstance(fields["colors"], list)
        or not fields["colors"]
        or not all(isinstance(c, str) and len(c) == 7 and c.startswith("#") for c in fields["colors"])
    ):
        raise ValueError("'colors' must be a non-empty list of #RRGGBB strings")
    if "sprite_type" in fields and fields["sprite_type"] not in sprite_types:
        raise ValueError(f"'sprite_type' must be one of {sorted(sprite_types)}")
    if "system_prompt" in fields and not isinstance(fields["system_prompt"], str):
        raise ValueError("'system_prompt' must be a string")
    return dict(fields)


def _render(canvas, params: dict[str, Any], steps: list[str], edit: bool) -> str:
    counts: dict[int, int] = {}
    for row in canvas.pixels:
        for v in row:
            counts[v] = counts.get(v, 0) + 1
    legend = []
    for idx, count in sorted(counts.items()):
        if idx < 0:
            legend.append(f". = transparent: {count}px")
        else:
            char = str(idx) if idx < 10 else chr(ord("A") + idx - 10)
            legend.append(f"{char} = {idx} ({canvas.palette[idx]}): {count}px")
    filled = sum(c for i, c in counts.items() if i >= 0)
    finished = any(s.startswith("tool_result: FINISHED") for s in steps)
    log = steps if len(steps) <= STEP_LOG_LIMIT else steps[:STEP_LOG_LIMIT] + [f"... {len(steps) - STEP_LOG_LIMIT} more steps"]
    return "\n".join([
        f"Texel Studio {'edit' if edit else 'generation'}: {params['prompt']}",
        f"Canvas: {canvas.size}x{canvas.size}, sprite_type={params['sprite_type']}, "
        f"filled {filled}/{canvas.size * canvas.size}px, finish called: {'yes' if finished else 'no'}, steps: {len(steps)}",
        "",
        "Final canvas (palette index per pixel, '.' = transparent):",
        canvas.to_visual_grid(),
        "",
        "Legend: " + "; ".join(legend),
        "",
        "Agent steps:",
        *log,
    ])


class TexelStudioBinding:
    def __init__(self):
        self._system_prompt, self._palette, self._sprite_types = _server_constants()
        self._native = None
        self._gen_id: str | None = None
        self._pixels: list[list[int]] | None = None
        self._params: dict[str, Any] | None = None
        self._closed = False

    def invoke(self, value, config=None):
        if self._closed:
            raise RuntimeError("Texel Studio binding is closed")
        from langchain_core.runnables.config import set_config_context

        request = _parse_input(value, self._sprite_types)
        if self._native is None:
            self._native = _load_native_agent()
        edit = self._params is not None
        if not edit:
            self._params = {
                "colors": request.get("colors", self._palette),
                "size": request.get("size", DEFAULT_SIZE),
                "system_prompt": request.get("system_prompt", self._system_prompt),
                "sprite_type": request.get("sprite_type", DEFAULT_SPRITE_TYPE),
            }
            thread = ((config or {}).get("configurable") or {}).get("thread_id")
            self._gen_id = str(thread) if thread else uuid.uuid4().hex
        params = {**self._params, "prompt": request["prompt"]}

        steps: list[str] = []

        def on_step(canvas, step_type, msg):
            steps.append(f"{step_type}: {msg}")

        with set_config_context(dict(config or {})) as ctx:
            canvas = ctx.run(
                self._native.run_agent_stream,
                gen_id=self._gen_id,
                message=params["prompt"],
                palette=params["colors"],
                size=params["size"],
                model_name=MODEL_NAME,
                style_prompt=params["system_prompt"],
                sprite_type=params["sprite_type"],
                reference_b64=None,
                on_step=on_step,
                existing_pixels=[row[:] for row in self._pixels] if self._pixels else None,
            )
        self._pixels = [row[:] for row in canvas.pixels]
        return {"answer": _render(canvas, params, steps, edit), "pixels": self._pixels, "steps": len(steps)}

    def close(self):
        self._closed = True
        self._native = None
        self._pixels = None


def create_graph():
    """Return a fresh binding; example input: 'a red health potion icon' or
    '{"prompt": "mossy stone block", "sprite_type": "block", "size": 16}'."""
    return TexelStudioBinding()
