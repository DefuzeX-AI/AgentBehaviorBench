"""Page-driven chat: one ChatSession answered in the background, plus marks.

The viewer's HTTP handler stays thin; this controller owns the turn order, the
live trajectory preview and reviewer marks, which are written straight into
the saved trajectory once the chat has ended. A turn runs in a worker thread so
the page can poll the conversation while the Agent answers. Only one turn runs
at a time, matching the Agent session's own sequential contract.
"""
from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from agentbench.trajectory.atif import marks
from .chat import ChatSession

PHASES = ("starting", "ready", "busy", "stopped", "ending", "ended")


def _now():
    return datetime.now(timezone.utc).isoformat()


class ChatController:
    def __init__(self, agent, *, output, environ, timeout=None, session_factory=ChatSession,
                 preview=None):
        self.agent = agent
        self.chat = session_factory(agent, output=output, environ=environ, timeout=timeout)
        self.lock = threading.RLock()
        self.turns = []
        self.phase = "starting"
        self.error = None
        self.run = None
        self.ended = threading.Event()
        self._preview = preview
        self._cached = (None, None)

    @property
    def directory(self):
        return self.chat.directory

    def start(self):
        try:
            directory = self.chat.start()
        except BaseException as exc:
            with self.lock:
                self.phase, self.error = "stopped", f"{type(exc).__name__}: {exc}"
            raise
        with self.lock:
            self.phase = "ready"
        return directory

    # -- turns -------------------------------------------------------------
    def submit(self, value):
        if isinstance(value, str) and not value.strip():
            raise ValueError("A turn needs some input")
        with self.lock:
            if self.phase != "ready":
                raise RuntimeError(f"The chat cannot accept a turn while it is {self.phase}")
            record = {"turn": len(self.turns) + 1, "input": value, "status": "pending", "sent_at": _now()}
            self.turns.append(record)
            self.phase = "busy"
        threading.Thread(target=self._answer, args=(record,), name="abb-chat-turn", daemon=True).start()
        return dict(record)

    def _answer(self, record):
        try:
            result = self.chat.send(record["input"])
        except Exception as exc:  # noqa: BLE001 - the page shows the failure
            with self.lock:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}", answered_at=_now())
                if self.phase == "busy":
                    self.phase, self.error = "stopped", record["error"]
            return
        with self.lock:
            record.update(status=result.get("status"), answered_at=_now())
            if result.get("status") == "succeeded":
                record["output"] = result.get("output")
            else:
                record["error"] = result.get("error", "unknown error")
            if self.phase == "busy":
                if result.get("session_usable") is False:
                    self.phase, self.error = "stopped", "The Agent session is no longer usable"
                else:
                    self.phase = "ready"

    def raw(self, number):
        """Recorded request, input and result of one turn, as saved."""
        directory = self.chat.directory / "steps" / f"{int(number):04d}"
        found = {}
        for name in ("input", "request", "result"):
            path = directory / f"{name}.json"
            if path.is_file():
                found[name] = json.loads(path.read_text(encoding="utf-8"))
        if not found:
            raise KeyError(number)
        return found

    # -- end ---------------------------------------------------------------
    def end(self, *, wait=False):
        """Stop the Agent, save the trajectory and record paths; idempotent."""
        with self.lock:
            if self.phase in ("ending", "ended"):
                thread = None
            else:
                status = "interrupted" if self.phase == "busy" else "succeeded"
                self.phase = "ending"
                thread = threading.Thread(target=self._close, args=(status,), name="abb-chat-end", daemon=True)
        if thread is not None:
            thread.start()
        if wait:
            self.ended.wait()

    def _close(self, status):
        error = "Ended while the Agent was answering" if status == "interrupted" else None
        try:
            run = self.chat.close(status, error)
        except Exception as exc:  # noqa: BLE001
            run = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        with self.lock:
            self.run, self.phase = run, "ended"
            self._cached = (None, None)
        self.ended.set()

    def state(self):
        with self.lock:
            run = self.run or {}
            return {"agent_id": self.agent.agent_id, "phase": self.phase, "error": self.error,
                    "run_id": self.chat.directory.name if self.chat.directory else None,
                    "directory": str(self.chat.directory) if self.chat.directory else None,
                    "turns": [dict(turn) for turn in self.turns],
                    "result": {key: run.get(key) for key in ("status", "error", "atif", "failed_turns")} if run else None,
                    "trajectory_path": self._saved_trajectory() if self.phase == "ended" else None}

    def _saved_trajectory(self):
        path = self.chat.directory / "trajectory.atif.json" if self.chat.directory else None
        return str(path) if path is not None and path.is_file() else None

    # -- trajectory and marks ---------------------------------------------
    def _signature(self):
        directory = self.chat.directory
        files = [path for name in ("steps", "otel") if (directory / name).is_dir()
                 for path in sorted((directory / name).rglob("*")) if path.is_file()]
        files += [path for path in (directory / "logs/network.jsonl", directory / "trajectory.atif.json") if path.is_file()]
        return tuple((str(path), path.stat().st_size, path.stat().st_mtime_ns) for path in files)

    def trajectory(self):
        """The saved trajectory once the chat ended, else a live preview."""
        if self.chat.directory is None:
            return {"status": "pending", "steps": 0}
        with self.lock:
            ended, run = self.phase == "ended", dict(self.run or self.chat.run or {})
        signature = (ended, self._signature())
        cached_signature, cached = self._cached
        if cached_signature == signature:
            return cached
        saved = self.chat.directory / "trajectory.atif.json"
        try:
            if ended:
                if not saved.is_file():
                    atif = run.get("atif") or {}
                    payload = {"status": atif.get("status", "unavailable"), "saved": False,
                               "error": atif.get("error") or atif.get("reason")}
                    self._cached = (signature, payload)
                    return payload
                document, status = json.loads(saved.read_text(encoding="utf-8")), (run.get("atif") or {}).get("status")
            else:
                if not any(turn.get("answered_at") for turn in self.turns):
                    return {"status": "pending", "steps": 0}
                preview = self._preview
                if preview is None:
                    from agentbench.trajectory.atif.attempt import preview
                document, validation = preview(self.chat.directory, run={**run, "status": "running"})
                status = validation.get("status")
        except ModuleNotFoundError as exc:
            payload = {"status": "unavailable", "error": f"Harbor is not installed ({exc.name})"}
        except Exception as exc:  # noqa: BLE001 - keep showing the last good preview
            if cached is not None and cached.get("document") is not None:
                return {**cached, "warning": f"{type(exc).__name__}: {exc}"}
            payload = {"status": "failed", "error": f"{type(exc).__name__}: {exc}"}
        else:
            payload = {"status": status, "saved": ended, "document": document}
        self._cached = (signature, payload)
        return payload

    def mark(self, trajectory_id, step_id, reason):
        """Write one mark into the saved trajectory at once."""
        self._require_saved()
        mark, digest = marks.add(self.chat.directory, trajectory_id, step_id, reason)
        self._recorded(digest)
        return mark

    def unmark(self, trajectory_id, step_id, created_at):
        self._require_saved()
        self._recorded(marks.remove(self.chat.directory, trajectory_id, step_id, created_at))

    def _require_saved(self):
        with self.lock:
            saved = self.phase == "ended" and (self.chat.directory / "trajectory.atif.json").is_file()
        if not saved:
            raise RuntimeError("Steps can be marked once the chat has ended and trajectory.atif.json is saved")

    def _recorded(self, digest):
        """Keep run.json's trajectory hash in step with the edited file."""
        with self.lock:
            run = self.run
            if run and isinstance(run.get("atif"), dict):
                run["atif"]["sha256"] = digest
                from .store import atomic_json
                atomic_json(self.chat.directory / "run.json", run)
            self._cached = (None, None)
