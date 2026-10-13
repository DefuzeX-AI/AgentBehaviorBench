"""Trusted controller client; mailbox contains current inputs and Agent outputs only."""
import asyncio
import json
import time
from pathlib import Path

from agentbench.observe.store import atomic_json
from .context import REQUESTS, RESPONSES
from .telemetry import decode_span

# Finite transport budget, independent of SDK evidence retention budgets.
MAX_BYTES = 128 * 1024 * 1024
MAX_FILES = 20000


def collect_response(source, destination):
    # All reads are relative to held directory descriptors. O_NOFOLLOW and
    # O_NONBLOCK reject symlink swaps and FIFOs created by an Agent, including
    # while copying. This client runs in the Linux controller container.
    import os
    import stat
    total, count = 0, 0
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK

    def visit(fd, relative):
        nonlocal total, count
        for name in os.listdir(fd):
            count += 1
            if count > MAX_FILES:
                raise ValueError('Agent response exceeds file transport limit')
            current = relative / name
            if current.parts[0] in ('done.json', 'input.json', 'request.json',
                                    'context.json', 'mapped-input.json'):
                continue
            handle = os.open(name, flags, dir_fd=fd)
            try:
                info = os.fstat(handle)
                if stat.S_ISDIR(info.st_mode):
                    visit(handle, current)
                elif stat.S_ISREG(info.st_mode):
                    target = destination / current
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with target.open('wb') as stream:
                        while block := os.read(handle, 65536):
                            total += len(block)
                            if total > MAX_BYTES:
                                raise ValueError('Agent response exceeds transport byte limit')
                            stream.write(block)
                else:
                    raise ValueError('Agent response contains a special file')
            finally:
                os.close(handle)

    fd = os.open(source, flags | os.O_DIRECTORY)
    try:
        visit(fd, Path())
    finally:
        os.close(fd)


def read_completion(folder):
    import os
    import stat
    flags = os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK
    parent = os.open(folder, flags | os.O_DIRECTORY)
    try:
        fd = os.open('done.json', flags, dir_fd=parent)
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError('Agent completion must be a regular file')
            data = os.read(fd, 16385)
            if len(data) > 16384:
                raise ValueError('Agent completion exceeds protocol limit')
            value = json.loads(data)
            if not isinstance(value, dict) or not isinstance(value.get('session'), dict):
                raise ValueError('Invalid Agent completion')
            return value
        finally:
            os.close(fd)
    finally:
        os.close(parent)


class DirectoryAgentSession:
    def __init__(self, *, timeout=2400, requests=Path(REQUESTS), responses=Path(RESPONSES)):
        self.requests, self.responses = Path(requests), Path(responses)
        self.timeout = timeout
        self.sequence = 0
        self.closed = False
        self.state = {'invocations': 0, 'closed': False}

    async def _exchange(self, envelope, timeout):
        sequence = self.sequence
        self.sequence += 1
        request = self.requests / f'{sequence:08d}.json'
        atomic_json(request, envelope)
        request.chmod(0o644)
        folder = self.responses / f'{sequence:08d}'
        deadline = time.monotonic() + timeout
        while not (folder / 'done.json').is_file():
            if time.monotonic() >= deadline:
                raise TimeoutError('Isolated Agent did not complete its current request')
            await asyncio.sleep(0.05)
        if folder.is_symlink() or (folder / 'done.json').is_symlink():
            raise ValueError('Agent completion cannot be a link')
        done = read_completion(folder)
        if done.get('sequence') != sequence:
            raise ValueError('Agent response identity mismatch')
        self.state = done['session']
        # The Agent never needs an old request to maintain its own conversation.
        request.unlink()
        return folder

    async def invoke(self, envelope, output, evidence):
        if self.closed:
            raise RuntimeError('Isolated Agent session is closed')
        folder = await self._exchange(dict(envelope), self.timeout)
        collect_response(folder, output)
        result = json.loads((output / 'result.json').read_text(encoding='utf-8'))
        if result.get('run_id') != envelope['run_id']:
            raise ValueError('Agent result belongs to a different invocation')
        spans = output / 'spans.jsonl'
        if not spans.is_file():
            raise ValueError('Agent response is missing original telemetry')
        with spans.open(encoding='utf-8') as stream:
            for line in stream:
                evidence.accept_span(decode_span(json.loads(line)))
        return result

    async def aclose(self):
        if not self.closed:
            self.closed = True
            await self._exchange({'operation': 'close'}, min(10, self.timeout))

    def snapshot(self):
        return dict(self.state)
