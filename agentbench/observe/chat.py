"""Interactive multi-turn chat with one Agent session, without Cases or a Judge.

The host starts the Agent's worker image once, with the chat worker as its
command, and exchanges turns through the mailbox in
``agentbench.runtime.agentcontainer.mailbox``. The attempt directory uses the
SDK step layout (request/, steps/NNNN/, otel/, logs/), and the ATIF trajectory
is derived after the container stops and host trace validation ran.
"""
from __future__ import annotations

import json
import subprocess
import time
from pathlib import Path
from uuid import uuid4

from agentbench.runtime.agentcontainer import mailbox
from agentbench.runtime.agentcontainer.config import runtime_type, execution_strategy, tomllib
from agentbench.runtime.docker import DockerRuntime
from agentbench.runtime.source import prepare_agent_source
from .store import TraceStore, atomic_json, summarize

EXIT_COMMANDS = frozenset({"/exit", "/quit"})
# The worker closes the Agent session (ACP processes, OTel export) after the end marker.
SHUTDOWN_SECONDS = 120


class ChatError(RuntimeError):
    """The chat container stopped answering; its records are kept."""


def chat_argv(root):
    """Launch the chat worker with the interpreter the one-shot worker uses."""
    manifest = tomllib.loads((Path(root) / "agent.toml").read_text(encoding="utf-8"))
    argv = list((manifest.get("launch") or {}).get("argv") or ())
    if len(argv) < 3 or argv[-2:] != ["-m", mailbox.ONESHOT_MODULE]:
        raise ValueError(f"Chat requires [launch] argv to end with '-m {mailbox.ONESHOT_MODULE}'")
    return [*argv[:-1], mailbox.WORKER_MODULE]


def record_paths(directory):
    """Existing records of a chat attempt, in reading order, as (label, path)."""
    directory = Path(directory)
    entries = [
        ("Run status", "run.json"),
        ("ATIF trajectory", "trajectory.atif.json"),
        ("Turn requests", "request/turns"),
        ("Agent target snapshot", "request/target.json"),
        ("Execution environment", "request/execution-environment.json"),
        ("Agent OTel spans", "otel/spans.jsonl"),
        ("Model/tool interceptor trace", "logs/network.jsonl"),
        ("Egress trace", "egress.jsonl"),
        ("Container stdout/stderr", "diagnostics.json"),
        ("Docker build logs", "docker-build"),
    ]
    found = [("Run directory", directory)]
    found += [(label, directory / name) for label, name in entries if (directory / name).exists()]
    steps = directory / "steps"
    if steps.is_dir():
        found += [(f"Turn {step.name} (request, result, framework/ACP events)", step)
                  for step in sorted(steps.iterdir()) if step.is_dir()]
    return found


class ChatSession:
    """One Agent container and Agent session for the lifetime of a chat."""

    def __init__(self, agent, *, output, environ, timeout=None, runtime_factory=DockerRuntime, poll=0.2):
        self.agent = agent
        self.output = Path(output)
        self.environ = dict(environ)
        self.timeout = timeout
        self.runtime_factory = runtime_factory
        self.poll = poll
        self.directory = self.session = self.checkpoint = None
        self.turns = []
        self.run = None

    def start(self):
        agent = self.agent
        if runtime_type(agent.path) != "docker" or execution_strategy(agent.path) != "oneshot":
            raise ValueError("Chat requires runtime.type=docker and execution=oneshot")
        argv = chat_argv(agent.path)
        prepare_agent_source(agent.path, output_fn=lambda message: print(message, flush=True))
        self.output.mkdir(parents=True, exist_ok=True, mode=0o700)
        # Short run IDs, like Suite and attempt IDs; creating the directory claims one.
        for _ in range(100):
            run_id = uuid4().hex[:8]
            directory = self.output.resolve() / run_id
            try:
                # The container's own UID writes steps/ and otel/ here, as in SDK attempts.
                directory.mkdir(mode=0o777)
                break
            except FileExistsError:
                continue
        else:
            raise RuntimeError("No unused chat run ID after 100 attempts")
        directory.chmod(0o777)
        self.directory = directory
        self.inputs = directory / "request"
        (self.inputs / "turns").mkdir(parents=True)
        # The interceptor trace is appended from the first model call on.
        (directory / "logs").mkdir()
        self.run = {"schema": "abb.chat.run.v1", "run_id": run_id, "agent_id": agent.agent_id,
                    "status": "running", "turns": self.turns}
        atomic_json(directory / "run.json", self.run)
        from agentbench.trajectory.metadata import capture_target
        atomic_json(self.inputs / "target.json", capture_target(agent.path))
        store = TraceStore(directory / "logs/network.jsonl", run_id, source="interceptor", environ=self.environ)
        runtime = self.runtime_factory(environ=self.environ, trace_sink=store, artifact_root=directory,
                                       timeout_sec=self.timeout, run_id=run_id)
        self.turn_timeout = runtime.invocation_timeout(agent)
        self.session = runtime.start(agent, invocation=(self.inputs, directory),
                                     argv=[*argv, "--session-id", run_id])
        self.checkpoint = self.session.trace_checkpoint()
        return directory

    def send(self, value):
        """Deliver one turn and wait for the Agent's result envelope."""
        number = len(self.turns) + 1
        mailbox.post(mailbox.turn_path(self.inputs, number), mailbox.turn(number, value))
        folder = mailbox.step_directory(self.directory, number)
        path = folder / "result.json"
        deadline = time.monotonic() + self.turn_timeout
        while not path.is_file():
            code = self.session.returncode
            if code is not None:
                raise ChatError(f"Agent container exited ({code}) before answering turn {number}")
            if time.monotonic() > deadline:
                raise ChatError(f"Agent did not answer turn {number} within {self.turn_timeout:g} s")
            time.sleep(self.poll)
        result = json.loads(path.read_text(encoding="utf-8"))
        self.turns.append({"turn": number, "status": result.get("status"),
                           "directory": folder.relative_to(self.directory).as_posix()})
        return result

    def close(self, status="succeeded", error=None):
        """Stop the container, validate traces, derive ATIF and save run.json."""
        run = self.run
        if run is None:
            return None
        if self.session is not None:
            try:
                if status == "succeeded":
                    mailbox.post(mailbox.end_path(self.inputs), {"schema": mailbox.SCHEMA, "end": True})
                    try:
                        run["exit_code"] = code = self.session.wait(timeout=SHUTDOWN_SECONDS)
                    except subprocess.TimeoutExpired:
                        status, error = "failed", f"Chat worker did not stop within {SHUTDOWN_SECONDS} s"
                    else:
                        if code != 0:
                            status, error = "failed", f"Chat worker exited {code}"
                        else:
                            run["host_trace_validation"] = "failed"
                            self.session.validate_trace(self.checkpoint)
                            run["host_trace_validation"] = "succeeded"
            except Exception as exc:  # noqa: BLE001 - records are kept and reported
                status, error = "failed", f"{type(exc).__name__}: {exc}"
            finally:
                try:
                    self.session.close()
                except Exception as exc:  # noqa: BLE001
                    status, error = "failed", error or f"Container cleanup failed: {exc}"
                atomic_json(self.directory / "diagnostics.json", {
                    "returncode": self.session.returncode, "stdout": self.session.stdout,
                    "stderr": self.session.stderr})
        run["status"] = status
        if error:
            run["error"] = error
        run["failed_turns"] = sum(1 for item in self.turns if item["status"] != "succeeded")
        run["trace_summary"] = summarize(self.directory)
        if self.turns:
            from agentbench.trajectory.atif import attempt
            run["atif"] = attempt.write(self.directory, run=run, environ=self.environ)
        else:
            run["atif"] = {"status": "skipped", "reason": "No turns were sent"}
        atomic_json(self.directory / "run.json", run)
        return run


def _text(value):
    return value if isinstance(value, str) else json.dumps(value, ensure_ascii=False, indent=2)


def run_chat(agent, *, output, environ, timeout=None, read=input, write=print, session_factory=ChatSession):
    """Converse until /exit, end of input or Ctrl+C; return the saved run status."""
    chat = session_factory(agent, output=output, environ=environ, timeout=timeout)
    write(f"Starting {agent.agent_id}; the first image build can take several minutes.")
    status, error = "succeeded", None
    try:
        directory = chat.start()
        write(f"Run: {directory.name}\nChatting with {agent.agent_id}. Type /exit to end.")
        while True:
            try:
                text = read("You: ")
            except (EOFError, KeyboardInterrupt):
                write("")
                break
            if text.strip() in EXIT_COMMANDS:
                break
            if not text.strip():
                continue
            result = chat.send(text)
            if result.get("status") == "succeeded":
                write(f"{agent.agent_id}: {_text(result.get('output'))}")
                continue
            write(f"[turn failed: {result.get('status')}] {result.get('error', 'unknown error')}")
            if result.get("session_usable") is False:
                write("The Agent session is no longer usable; ending the chat.")
                break
    except KeyboardInterrupt:
        status, error = "interrupted", "Interrupted while the Agent was answering"
    except Exception as exc:  # noqa: BLE001 - the chat ends but its records are kept
        status, error = "failed", f"{type(exc).__name__}: {exc}"
        write(f"Chat failed: {error}")
    write("Ending the chat and saving records...")
    run = chat.close(status, error)
    if run is not None:
        report(run, chat.directory, write)
    return run


def report(run, directory, write=print):
    """Print the outcome of a closed chat and the paths of its records."""
    atif = run.get("atif") or {}
    write(f"Status: {run['status']}  turns: {len(run.get('turns') or [])}  "
          f"trajectory: {atif.get('status')}" + (f" ({atif['steps']} steps)" if "steps" in atif else ""))
    if run.get("error"):
        write(f"Error: {run['error']}")
    write("Records:")
    for label, path in record_paths(directory):
        write(f"  {label}: {path}")
