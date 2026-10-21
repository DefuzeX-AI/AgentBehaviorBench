"""Run native command strings inside ABB's existing Agent container.

This replaces Docker *transport*, not native command construction or tools.
No host socket, host mount, extra network namespace or privileged runner is used.
Persistent calls share one bash process, like the upstream runner.
"""
from __future__ import annotations

import os
import re
import selectors
import subprocess
import threading
import time
import uuid


class ContainerBashProcess:
    instances = set()
    def __init__(self, strip_newlines=False, return_err_output=False,
                 persistent=False, workdir="/", mounted_dirs=None,
                 runner_image=None, docker_platform=None, privileged=None):
        self.instances.add(self)
        self.strip_newlines = strip_newlines
        self.return_err_output = return_err_output
        self.persistent = persistent
        self.workdir = workdir or "/"
        self.process = None
        self.lock = threading.Lock()
        self.timeout = int(os.environ.get("DECOMPAI_TOOL_TIMEOUT", "60"))

    def run(self, commands, filter_color_codes=True):
        self.instances.add(self)
        command = commands if isinstance(commands, str) else ";".join(commands)
        if not isinstance(command, str):
            raise TypeError("Shell commands must be text")
        with self.lock:
            if not self.persistent:
                p = subprocess.run(["/bin/bash", "-c", command], cwd=self.workdir,
                                   capture_output=True, text=True, timeout=self.timeout)
                output = p.stdout + ("\n=== STDERR ===\n" + p.stderr if p.stderr else "")
            else:
                if self.process is None or self.process.poll() is not None:
                    self.process = subprocess.Popen(
                        ["/bin/bash"], cwd=self.workdir, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, bufsize=0)
                marker = ("__ABB_DONE_" + uuid.uuid4().hex + "__").encode()
                self.process.stdin.write(command.encode() + b"\nprintf '\\n" + marker + b"\\n'\n")
                self.process.stdin.flush()
                selector = selectors.DefaultSelector()
                selector.register(self.process.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + self.timeout
                chunks = b""
                try:
                    while marker not in chunks:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(max(0, remaining)):
                            self.stop_persistent_container()
                            raise TimeoutError("Native tool command exceeded the deployment timeout")
                        block = os.read(self.process.stdout.fileno(), 65536)
                        if not block:
                            raise RuntimeError("Native persistent shell ended before its completion marker")
                        chunks += block
                    output = chunks.split(marker, 1)[0].decode(errors="replace")
                finally:
                    selector.close()
        if filter_color_codes:
            output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", output)
        return output.strip() if self.strip_newlines else output

    def stop_persistent_container(self):
        if self.process is not None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
            self.process = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop_persistent_container()


def install(native_utils, shell_module):
    """Adapt both native subprocess paths without editing imported source."""
    def run_command(command):
        output = subprocess.run(["/bin/sh", "-c", command], capture_output=True,
                                text=True, timeout=int(os.environ.get("DECOMPAI_TOOL_TIMEOUT", "60")))
        combined = output.stdout
        if output.stderr:
            combined += "\n=== STDERR ===\n" + output.stderr
        return native_utils.CommandResult(output.stdout, output.stderr, combined)

    native_utils.run_command_in_docker = run_command
    shell_module.DockerizedBashProcess = ContainerBashProcess


def close_all():
    for process in list(ContainerBashProcess.instances):
        process.stop_persistent_container()
        ContainerBashProcess.instances.discard(process)
