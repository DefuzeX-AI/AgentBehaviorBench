"""ABB text boundary for EvoScientist/EvoScientist (main ``EvoScientist`` graph).

Upstream entrypoints (source under ``agent/`` is unchanged):

* ``EvoScientist/langgraph_dev/langgraph.json`` graph ``EvoScientist`` -> the main
  deep-agent orchestrator (planner / research / code / debug / data-analysis / writing
  sub-agents, think_tool, skill_manager, file-system + ``execute`` sandbox tools,
  QuickJS code interpreter, memory middleware).
* This binding builds that same graph the way the upstream one-shot CLI does
  (``EvoSci -p "<prompt>" --auto-mode``, ``cli/commands.py``): it resolves the config with
  ``get_effective_config(cli_overrides)`` and calls
  ``EvoScientist.EvoScientist.create_cli_agent(workspace_dir=..., config=...)``
  (InMemorySaver checkpointer, one thread per ABB session).

Deployment settings (all upstream config keys, passed as CLI overrides):

* ``provider = "zhipu-code"``, ``model = $GLM_MODEL``: upstream's built-in Zhipu GLM Coding
  Plan provider (ChatOpenAI against ``https://open.bigmodel.cn/api/coding/paas/v4``, key from
  ``ZHIPU_API_KEY``). ABB intercepts that route and substitutes the credential.
* ``auto_mode = True`` (implies ``auto_approve``, ``enable_ask_user = False``): upstream's
  unattended mode, the same overrides ``--auto-mode`` applies. The run config carries
  ``configurable.hitl_suppressed = True`` like upstream's gateways write for an auto-mode
  run, so the always-armed HITL interrupts do not park the graph.
* ``enable_async_subagents = False`` / ``enable_scheduler = False``: no ``langgraph dev``
  sidecar server (upstream's documented setting for short scripted one-shot runs); the
  writing / data-analysis sub-agents run in-process, cron scheduling is off.
* ``memory_workers_enabled = False`` / ``memory_skill_synthesis_enabled = False``: the
  post-turn background memory workers and skill synthesis are off (they persist across
  sessions, which a disposable one-shot container cannot keep, and would run LLM calls
  after the reply). Profile/observation memory reading stays on (empty per Case).
* ``recursion_limit = 150`` (upstream default 1,000,000 = "effectively unlimited"): bounds
  one turn so a Case finishes within the container timeout.
* No ``TAVILY_API_KEY``: upstream then omits ``tavily_search``; no web search.

The Case Input is the user message; the reply is the text of the final AI message.
The full message list is returned as raw output for evidence.
"""
import os
import tempfile
import uuid
from collections.abc import Mapping

RECURSION_LIMIT = 150


def _text(message):
    content = getattr(message, "content", None)
    if content is None and isinstance(message, Mapping):
        content = message.get("content")
    if isinstance(content, list):
        content = "".join(
            part.get("text", "") if isinstance(part, Mapping) else str(part)
            for part in content
            if not isinstance(part, Mapping) or part.get("type", "text") == "text"
        )
    return content if isinstance(content, str) else ("" if content is None else str(content))


def _message_record(message):
    record = {"type": getattr(message, "type", None), "content": _text(message)}
    name = getattr(message, "name", None)
    if name:
        record["name"] = name
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        record["tool_calls"] = [{"name": c.get("name"), "args": c.get("args")} for c in tool_calls]
    return record


class EvoScientistGraph:
    def __init__(self):
        model = os.environ.get("GLM_MODEL", "").strip()
        if not model:
            raise RuntimeError("GLM_MODEL is required")
        if not os.environ.get("ZHIPU_API_KEY"):
            raise RuntimeError("ZHIPU_API_KEY is required")
        # Disposable per-session state: workspace (agent files, memories, skills), data dir
        # (sessions.db) and config dir all live under /tmp; nothing persists past the Case.
        self._root = tempfile.mkdtemp(prefix="evoscientist-")
        self._workspace = os.path.join(self._root, "workspace")
        os.makedirs(self._workspace)
        os.environ["EVOSCIENTIST_WORKSPACE_DIR"] = self._workspace
        os.environ["EVOSCIENTIST_DATA_DIR"] = os.path.join(self._root, "data")
        os.environ["XDG_CONFIG_HOME"] = os.path.join(self._root, "config")
        # Upstream's CLI uses the working directory as the default workspace.
        os.chdir(self._workspace)

        from EvoScientist.config.settings import apply_config_to_env, get_effective_config
        from EvoScientist.EvoScientist import create_cli_agent
        from EvoScientist.paths import ensure_dirs, set_workspace_root

        overrides = {
            "provider": "zhipu-code",
            "model": model,
            "auto_mode": True,
            "auto_approve": True,
            "enable_ask_user": False,
            "enable_async_subagents": False,
            "enable_scheduler": False,
            "memory_workers_enabled": False,
            "memory_skill_synthesis_enabled": False,
            "recursion_limit": RECURSION_LIMIT,
            "ui_backend": "cli",
        }
        self._config = get_effective_config(overrides)
        apply_config_to_env(self._config)
        set_workspace_root(self._workspace)
        ensure_dirs()
        self._agent = create_cli_agent(workspace_dir=self._workspace, config=self._config)

    def _run_config(self, config):
        from EvoScientist.cli._constants import build_metadata

        run_config = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        configurable.setdefault("thread_id", str(uuid.uuid4()))
        # Same key upstream's gateways write for an auto-mode run (gateway/types.py).
        configurable["hitl_suppressed"] = True
        run_config["configurable"] = configurable
        metadata = dict(run_config.get("metadata") or {})
        metadata.update(build_metadata(self._workspace, self._config.model))
        run_config["metadata"] = metadata
        run_config.setdefault("recursion_limit", RECURSION_LIMIT)
        return run_config

    @staticmethod
    def _input(value):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        return {"messages": [{"role": "user", "content": text}]}

    def _result(self, state):
        messages = list(state.get("messages") or []) if isinstance(state, Mapping) else []
        interrupts = state.get("__interrupt__") if isinstance(state, Mapping) else None
        if interrupts:
            raise RuntimeError(f"EvoScientist paused on an interrupt nobody can answer: {interrupts!r}"[:2000])
        answer = ""
        for message in reversed(messages):
            if getattr(message, "type", None) == "ai" and _text(message).strip():
                answer = _text(message)
                break
        if not answer.strip():
            raise RuntimeError("EvoScientist returned no final AI message")
        return {
            "answer": answer,
            "messages": [_message_record(m) for m in messages],
            "workspace_files": sorted(
                os.path.relpath(os.path.join(d, f), self._workspace)
                for d, _, files in os.walk(self._workspace) for f in files
            )[:200],
        }

    def invoke(self, value, config=None, **kwargs):
        return self._result(self._agent.invoke(self._input(value), config=self._run_config(config)))

    async def ainvoke(self, value, config=None, **kwargs):
        return self._result(await self._agent.ainvoke(self._input(value), config=self._run_config(config)))

    def close(self):
        self._agent = None


def create_graph():
    return EvoScientistGraph()
