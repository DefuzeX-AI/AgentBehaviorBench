"""ABB boundary for lfnovo/open-notebook's notebook chat (open_notebook/graphs/chat.py).

The invoked graph is upstream's compiled ``open_notebook.graphs.chat.graph`` (SqliteSaver
checkpointer, one ``agent`` node that provisions the configured chat model through
Esperanto). The binding reproduces what upstream's API does around that graph
(api/main.py lifespan + api/routers/chat.py create_session / build_context /
execute_chat), without the FastAPI/Next.js layers:

* per Case it starts a disposable in-memory SurrealDB (``surreal start memory``) inside
  the container - upstream's own ``single`` image runs SurrealDB in-container too - and
  applies upstream's migrations with ``AsyncMigrationManager``;
* it registers one ``openai_compatible`` language model (name = ``$GLM_MODEL``) and
  makes it the default chat model, i.e. what "Manage -> Models" does; the endpoint and
  key come from upstream's documented env fallback ``OPENAI_COMPATIBLE_BASE_URL`` /
  ``OPENAI_COMPATIBLE_API_KEY`` (mapped from ``GLM_API_BASE_URL`` / ``GLM_API_KEY``);
* it creates one empty Notebook and one ChatSession related to it;
* each Case Input is one user chat message: the binding loads the session's
  checkpointed state, builds the notebook context with upstream's
  ``build_notebook_context`` (empty - no sources/notes are uploaded through the text
  boundary), appends the HumanMessage and invokes the graph with
  ``thread_id = <chat session id>``, exactly as ``execute_chat`` does.

The answer is the content of the last AI message the graph returned. Native exceptions
are not swallowed. Nothing is fabricated: no reply is produced outside the graph.
"""
import asyncio
import os
import shutil
import subprocess
import tempfile
import time
from collections.abc import Mapping


SURREAL_PORT = 18765


def _wait_ready(log_path, proc, timeout=60):
    # Readiness is read from SurrealDB's own log: in the ABB container every TCP
    # connect (loopback included) is redirected to the interceptor, so a port probe
    # would succeed before the database is listening.
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"SurrealDB exited early with code {proc.returncode}")
        with open(log_path, "rb") as log:
            if b"Started web server" in log.read():
                return
        time.sleep(0.2)
    raise RuntimeError("SurrealDB did not start its web server in time")


class OpenNotebookChat:
    def __init__(self):
        model_name = os.environ.get("GLM_MODEL", "").strip()
        base_url = os.environ.get("GLM_API_BASE_URL", "").strip()
        api_key = os.environ.get("GLM_API_KEY", "").strip()
        if not model_name or not base_url or not api_key:
            raise RuntimeError("GLM_MODEL, GLM_API_BASE_URL and GLM_API_KEY are required")
        # Upstream's documented env fallback for an OpenAI-compatible provider.
        os.environ["OPENAI_COMPATIBLE_BASE_URL"] = base_url
        os.environ["OPENAI_COMPATIBLE_API_KEY"] = api_key

        # open_notebook.config creates ./data (LangGraph SQLite checkpoints, uploads) under
        # the working directory at import time; /opt/agent is not writable, so the Case
        # runs from a disposable directory, like upstream's image runs from its /app volume.
        self._dir = tempfile.mkdtemp(prefix="open-notebook-")
        self._cwd = os.getcwd()
        os.chdir(self._dir)
        # Pinned: network/rules.toml admits exactly this loopback WebSocket route.
        port = SURREAL_PORT
        os.environ["SURREAL_URL"] = f"ws://127.0.0.1:{port}/rpc"
        os.environ.setdefault("SURREAL_USER", "root")
        os.environ.setdefault("SURREAL_PASSWORD", "root")
        os.environ.setdefault("SURREAL_NAMESPACE", "open_notebook")
        os.environ.setdefault("SURREAL_DATABASE", "open_notebook")
        self._port = port
        self._model_name = model_name
        self._log = None
        self._surreal = None
        self._session_id = None
        self._notebook_id = None

    async def _ensure_started(self):
        # The factory may be called inside ABB's running event loop, so the database
        # process and upstream's async bootstrap start on the first Case Input.
        if self._session_id is not None:
            return
        self._log = open(os.path.join(self._dir, "surreal.log"), "wb")
        self._surreal = subprocess.Popen(
            ["surreal", "start", "--log", "info", "--user", os.environ["SURREAL_USER"],
             "--pass", os.environ["SURREAL_PASSWORD"], "--bind", f"127.0.0.1:{self._port}", "memory"],
            stdout=self._log, stderr=subprocess.STDOUT, cwd=self._dir,
        )
        await asyncio.to_thread(_wait_ready, self._log.name, self._surreal)
        await self._bootstrap(self._model_name)

    async def _bootstrap(self, model_name):
        from open_notebook.ai.models import DefaultModels, Model
        from open_notebook.database.async_migrate import AsyncMigrationManager
        from open_notebook.domain.notebook import ChatSession, Notebook

        # Upstream reads its migration files relative to the repository root (its image
        # runs from /app); only this constructor runs from there.
        import open_notebook

        cwd = os.getcwd()
        os.chdir(os.path.dirname(os.path.dirname(open_notebook.__file__)))
        try:
            manager = AsyncMigrationManager()
        finally:
            os.chdir(cwd)
        for _ in range(50):
            try:
                await manager.ping()
                break
            except Exception:
                await asyncio.sleep(0.2)
        if await manager.needs_migration():
            await manager.run_migration_up()

        model = Model(name=model_name, provider="openai_compatible", type="language")
        await model.save()
        defaults = await DefaultModels.get_instance()
        defaults.default_chat_model = model.id
        await defaults.update()

        notebook = Notebook(name="ABB evaluation notebook",
                            description="Notebook created for one ABB evaluation Case; it has no sources or notes.")
        await notebook.save()
        session = ChatSession(title="ABB evaluation chat")
        await session.save()
        await session.relate_to_notebook(notebook.id)
        self._notebook_id = notebook.id
        self._session_id = session.id

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        await self._ensure_started()
        from langchain_core.messages import AIMessage, HumanMessage
        from langchain_core.runnables import RunnableConfig
        from open_notebook.domain.notebook import Notebook
        from open_notebook.graphs.chat import graph as chat_graph
        from open_notebook.utils.context_builder import build_notebook_context

        # Mirrors api/routers/chat.py: context comes from /chat/context, state from the
        # session checkpoint, thread_id is the chat session id.
        notebook = await Notebook.get(self._notebook_id)
        context, _ = await build_notebook_context(notebook, None)
        thread = {"thread_id": self._session_id}
        current = await asyncio.to_thread(chat_graph.get_state, config=RunnableConfig(configurable=thread))
        state = dict(current.values) if current else {}
        state["messages"] = list(state.get("messages", []))
        state["context"] = context
        state["notebook"] = notebook
        state["model_override"] = None
        state["messages"].append(HumanMessage(content=text))

        run_config = dict(config or {})
        configurable = dict(run_config.get("configurable") or {})
        configurable.update(thread_id=self._session_id, model_id=None)
        run_config["configurable"] = configurable
        result = await asyncio.to_thread(lambda: chat_graph.invoke(input=state, config=run_config))
        messages = result.get("messages", [])
        last = messages[-1] if messages else None
        if not isinstance(last, AIMessage):
            raise RuntimeError("Open Notebook chat graph returned no AI message")
        answer = last.content if isinstance(last.content, str) else str(last.content)
        if not answer.strip():
            raise RuntimeError("Open Notebook chat graph returned an empty reply")
        return {"answer": answer, "messages": messages, "session_id": self._session_id,
                "notebook_id": self._notebook_id, "context": context}

    def close(self):
        proc, self._surreal = getattr(self, "_surreal", None), None
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
        log = getattr(self, "_log", None)
        if log is not None:
            log.close()
        cwd = getattr(self, "_cwd", None)
        if cwd:
            os.chdir(cwd)
        shutil.rmtree(getattr(self, "_dir", ""), ignore_errors=True)


def create_graph():
    return OpenNotebookChat()
