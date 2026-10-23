"""ABB binding for ai-christianson/RA.Aid.

Native contract (source under ``agent/`` is unchanged):

1. **Entrypoint.** RA.Aid is the ``ra-aid`` CLI (``ra_aid.__main__:main``). Its
   documented unattended use is ``ra-aid -m "<task>" --cowboy-mode`` (README,
   "Command Line Options"): ``main()`` opens the project database under
   ``.ra-aid/``, applies migrations, records the input, then runs the research
   agent, which hands off to planning and implementation agents as needed. It
   prints its progress and results with Rich and returns nothing. The binding
   calls the same ``main()`` with that argument vector, captures what it prints,
   and treats ``SystemExit(0)`` as a normal end of the run.

2. **Provider.** The README's DeepSeek setup: ``--provider deepseek --model
   deepseek-chat`` with ``DEEPSEEK_API_KEY``. With only that key set,
   ``parse_arguments`` makes the expert model ``deepseek-reasoner`` on the same
   provider. Both reach ``api.deepseek.com``, the route ``agent.toml`` declares;
   ABB's interception replaces the request with the run model. Web research
   (``web_search_tavily``) is enabled when ``TAVILY_API_KEY`` is present.

3. **Project directory and turns.** RA.Aid works on the current directory. Each
   binding instance owns one empty temporary git repository (RA.Aid's tools use
   git and ripgrep) and removes it on ``close()``. Every Case input is one
   ``ra-aid -m`` run in that directory, so later inputs see earlier file changes
   and RA.Aid's own persisted memory (key facts, snippets, research notes in
   ``.ra-aid/``), as consecutive CLI runs in one project would.

4. **Configuration.** ``main()`` has no config parameter and builds its own
   LangGraph config; ABB's config is applied with ``set_config_context``.

5. **Process start (environment workaround).** ``ra_aid/proc/interactive.py``
   starts every shell command with ``subprocess.Popen(..., preexec_fn=os.setsid)``.
   With ``preexec_fn`` set, CPython runs ``os.register_at_fork`` child hooks in
   the forked child; the OpenTelemetry SDK that ABB's worker loads registers such
   hooks, and the child blocked on a futex before ``exec`` (observed: no shell
   command ever started). The binding gives that module a ``subprocess`` facade
   whose ``Popen`` turns exactly ``preexec_fn=os.setsid`` into
   ``start_new_session=True``, which performs the same ``setsid()`` in the
   child without running Python hooks. Commands, arguments, pty handling and
   timeouts are unchanged.

Output: ``{"answer": <console output of the run>, "exit_code", "files"}``.
A non-zero ``SystemExit`` or any other exception propagates.
"""

from __future__ import annotations

import contextlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1] / "agent"
BASE_ARGS = ["--cowboy-mode", "--provider", "deepseek", "--model", "deepseek-chat"]
MAX_LISTED_FILES = 200


def _text(value) -> str:
    if isinstance(value, Mapping):
        if set(value) != {"message"}:
            raise ValueError("Supply text or exactly {'message': text}")
        value = value["message"]
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Case input must be a non-empty task message")
    return value


def _install_session_start_facade() -> None:
    """Replace preexec_fn=os.setsid with start_new_session=True in RA.Aid's process module."""
    import types
    import ra_aid.proc.interactive as interactive

    if getattr(interactive.subprocess, "_abb_session_facade", False):
        return
    real = subprocess

    def popen(*args, **kwargs):
        if kwargs.get("preexec_fn") is os.setsid:
            kwargs.pop("preexec_fn")
            kwargs["start_new_session"] = True
        return real.Popen(*args, **kwargs)

    facade = types.ModuleType("subprocess")
    facade.__dict__.update({k: v for k, v in vars(real).items() if not k.startswith("__")})
    facade.Popen = popen
    facade._abb_session_facade = True
    interactive.subprocess = facade


def _list_files(root: Path) -> list[dict]:
    files = []
    for path in sorted(root.rglob("*")):
        rel = path.relative_to(root)
        if path.is_file() and rel.parts[0] not in {".git", ".ra-aid"}:
            files.append({"path": str(rel), "bytes": path.stat().st_size})
            if len(files) >= MAX_LISTED_FILES:
                break
    return files


class RaAidRun:
    def __init__(self):
        self._workspace = Path(tempfile.mkdtemp(prefix="ra-aid-project-"))
        subprocess.run(["git", "init", "-q"], cwd=self._workspace, check=True)

    def invoke(self, value, config=None):
        if self._workspace is None:
            raise RuntimeError("RA.Aid binding is closed")
        task = _text(value)
        if str(SOURCE_ROOT) not in sys.path:
            sys.path.insert(0, str(SOURCE_ROOT))
        from langchain_core.runnables.config import set_config_context
        from ra_aid.__main__ import main

        _install_session_start_facade()
        import ra_aid.__main__ as ra_main
        # The startup update check fetches docs.ra-aid.ai, which the sandbox egress
        # policy denies; RA.Aid already treats a failed check as "no message".
        ra_main.check_for_newer_version = lambda: ""
        buffer = io.StringIO()
        exit_code = 0
        previous_argv, previous_cwd = sys.argv, os.getcwd()
        sys.argv = ["ra-aid", "-m", task, *BASE_ARGS]
        os.chdir(self._workspace)
        try:
            with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
                with set_config_context(dict(config or {})) as ctx:
                    try:
                        ctx.run(main)
                    except SystemExit as exc:
                        exit_code = exc.code if isinstance(exc.code, int) else (0 if exc.code is None else 1)
        finally:
            sys.argv = previous_argv
            os.chdir(previous_cwd)
        output = buffer.getvalue()
        if exit_code != 0:
            raise RuntimeError(f"ra-aid exited with status {exit_code}:\n{output[-4000:]}")
        return {"answer": output, "exit_code": exit_code, "files": _list_files(self._workspace)}

    def close(self):
        workspace, self._workspace = self._workspace, None
        if workspace is not None:
            shutil.rmtree(workspace, ignore_errors=True)


def create_graph():
    """Return a fresh binding; example input: 'Create fizzbuzz.py and a test for it, then run the test.'"""
    return RaAidRun()
