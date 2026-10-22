"""Run unchanged native commands in ABB's existing non-root Linux container."""
from __future__ import annotations

import os
import re
import selectors
import signal
import subprocess
import threading
import time
import uuid


class NativeCommandTimeout(TimeoutError):
    """A real timeout retaining the output observed before process cleanup."""
    def __init__(self, seconds, stdout='', stderr=''):
        self.stdout, self.stderr = stdout, stderr
        message = f'Native tool command exceeded the deployment timeout ({seconds}s)'
        if stdout:
            message += '\n=== CAPTURED STDOUT BEFORE TIMEOUT ===\n' + stdout
        if stderr:
            message += '\n=== CAPTURED STDERR BEFORE TIMEOUT ===\n' + stderr
        super().__init__(message)


def _signal_group(process, value):
    # Every process managed here owns a new session, never the host caller's group.
    try:
        os.killpg(process.pid, value)
    except ProcessLookupError:
        pass


def _stop(process):
    _signal_group(process, signal.SIGTERM)
    try:
        process.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    finally:
        # A shell can exit before its children; still close its original group.
        _signal_group(process, signal.SIGKILL)
        process.wait(timeout=3)


def _run(argv, *, timeout, cwd=None):
    process = subprocess.Popen(argv, cwd=cwd, stdout=subprocess.PIPE,
                               stderr=subprocess.PIPE, text=True, start_new_session=True)
    try:
        stdout, stderr = process.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        _stop(process)
        stdout, stderr = process.communicate()
        raise NativeCommandTimeout(timeout, stdout, stderr) from None
    return subprocess.CompletedProcess(argv, process.returncode, stdout, stderr)


class ContainerBashProcess:
    instances = set()

    def __init__(self, strip_newlines=False, return_err_output=False,
                 persistent=False, workdir='/', mounted_dirs=None,
                 runner_image=None, docker_platform=None, privileged=None):
        self.instances.add(self)
        self.strip_newlines = strip_newlines
        self.return_err_output = return_err_output
        self.persistent = persistent
        self.workdir = workdir or '/'
        self.process = None
        self.lock = threading.Lock()
        self.timeout = int(os.environ.get('DECOMPAI_TOOL_TIMEOUT', '60'))

    def run(self, commands, filter_color_codes=True):
        self.instances.add(self)
        command = commands if isinstance(commands, str) else ';'.join(commands)
        if not isinstance(command, str):
            raise TypeError('Shell commands must be text')
        with self.lock:
            if not self.persistent:
                result = _run(['/bin/bash', '-c', command], cwd=self.workdir, timeout=self.timeout)
                output = result.stdout + ('\n=== STDERR ===\n' + result.stderr if result.stderr else '')
            else:
                if self.process is None or self.process.poll() is not None:
                    self.process = subprocess.Popen(
                        ['/bin/bash'], cwd=self.workdir, stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        bufsize=0, start_new_session=True)
                marker = ('__ABB_DONE_' + uuid.uuid4().hex + '__').encode()
                self.process.stdin.write(command.encode() + b"\nprintf '\\n" + marker + b"\\n'\n")
                self.process.stdin.flush()
                selector = selectors.DefaultSelector()
                selector.register(self.process.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + self.timeout
                chunks = b''
                try:
                    while marker not in chunks:
                        remaining = deadline - time.monotonic()
                        if remaining <= 0 or not selector.select(max(0, remaining)):
                            self.stop_persistent_container()
                            raise NativeCommandTimeout(self.timeout, chunks.decode(errors='replace'))
                        block = os.read(self.process.stdout.fileno(), 65536)
                        if not block:
                            self.stop_persistent_container()
                            raise RuntimeError('Native persistent shell ended before its completion marker; observed output:\n'
                                               + chunks.decode(errors='replace'))
                        chunks += block
                    output = chunks.split(marker, 1)[0].decode(errors='replace')
                finally:
                    selector.close()
        if filter_color_codes:
            output = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', output)
        return output.strip() if self.strip_newlines else output

    def stop_persistent_container(self):
        if self.process is not None:
            process, self.process = self.process, None
            _stop(process)
            for pipe in (process.stdin, process.stdout):
                if pipe:
                    try:
                        pipe.close()
                    except OSError:
                        pass

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.stop_persistent_container()


def install(native_utils, shell_module):
    """Adapt transport only; utility analysis gets a separately declared cold-start limit."""
    def run_command(command):
        output = _run(['/bin/sh', '-c', command], timeout=int(os.environ.get('DECOMPAI_ANALYSIS_TIMEOUT', '600')))
        combined = output.stdout
        if output.stderr:
            combined += '\n=== STDERR ===\n' + output.stderr
        return native_utils.CommandResult(output.stdout, output.stderr, combined)
    native_utils.run_command_in_docker = run_command
    shell_module.DockerizedBashProcess = ContainerBashProcess


def close_all():
    for process in list(ContainerBashProcess.instances):
        process.stop_persistent_container()
        ContainerBashProcess.instances.discard(process)
