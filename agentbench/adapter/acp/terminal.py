"""Session-owned callback terminals; continuously drain output with a byte bound."""
import asyncio
import os
import signal
from dataclasses import dataclass, field
from uuid import uuid4
from acp import RequestError
from acp.schema import (CreateTerminalResponse, TerminalOutputResponse, TerminalExitStatus,
                        WaitForTerminalExitResponse, KillTerminalResponse, ReleaseTerminalResponse)
from .filesystem import workspace_path
from .process import child_environment, terminate_group


@dataclass
class Terminal:
    process: object
    limit: int
    drain: object = None
    output: bytearray = field(default_factory=bytearray)
    truncated: bool = False

    async def collect(self):
        while chunk := await self.process.stdout.read(8192):
            self.output.extend(chunk)
            if len(self.output) > self.limit:
                self.truncated = True
                del self.output[:len(self.output) - self.limit]

    def status(self):
        code = self.process.returncode
        if code is None:
            return None
        return {'exit_code': code if code >= 0 else None,
                'signal': signal.Signals(-code).name if code < 0 else None}


class Terminals:
    def __init__(self, config, emit):
        self.config, self.emit = config, emit
        self.items = {}

    def get(self, identifier):
        if identifier not in self.items:
            raise RequestError.resource_not_found(identifier)
        return self.items[identifier]

    async def create(self, command, args=None, env=None, cwd=None, output_byte_limit=None):
        if not isinstance(command, str) or not command or '\0' in command:
            raise RequestError.invalid_params({'message': 'Invalid terminal command'})
        limit = self.config.max_output_bytes if output_byte_limit is None else output_byte_limit
        if type(limit) is not int or limit < 0:
            raise RequestError.invalid_params({'message': 'Invalid terminal output limit'})
        limit = min(limit, self.config.max_output_bytes)
        directory = workspace_path(self.config, cwd or self.config.cwd)
        environment = child_environment(self.config)
        environment.update({item.name: item.value for item in env or []})
        process = await asyncio.create_subprocess_exec(command, *(args or []), cwd=directory,
            env=environment, stdin=asyncio.subprocess.DEVNULL, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT, start_new_session=os.name == 'posix')
        identifier = uuid4().hex
        terminal = Terminal(process, limit)
        terminal.drain = asyncio.create_task(terminal.collect())
        self.items[identifier] = terminal
        self.emit('terminal_started', {'terminal_id': identifier, 'command': command, 'args': args or []})
        return CreateTerminalResponse(terminal_id=identifier)

    async def output(self, identifier):
        terminal = self.get(identifier)
        if terminal.drain.done():
            await terminal.drain
        status = terminal.status()
        # Dropping partial UTF-8 codepoints keeps the advertised byte limit intact.
        return TerminalOutputResponse(output=terminal.output.decode('utf-8', errors='ignore'),
            truncated=terminal.truncated, exit_status=TerminalExitStatus(**status) if status else None)

    async def wait(self, identifier):
        terminal = self.get(identifier)
        # asyncio's wait can include pipe EOF; detached descendants may retain the
        # pipe after the leader exits. Report the command exit without waiting on them.
        while terminal.process.returncode is None:
            await asyncio.sleep(0.01)
        self.emit('terminal_exited', {'terminal_id': identifier, **terminal.status()})
        return WaitForTerminalExitResponse(**terminal.status())

    async def kill(self, identifier):
        await terminate_group(self.get(identifier).process, self.config.cleanup_timeout)
        return KillTerminalResponse()

    async def release(self, identifier):
        terminal = self.get(identifier)
        try:
            await terminate_group(terminal.process, self.config.cleanup_timeout)
            result = await self.output(identifier)
            self.emit('terminal_released', {'terminal_id': identifier,
                **result.model_dump(mode='json', by_alias=True, exclude_none=True)})
        finally:
            terminal.drain.cancel()
            await asyncio.gather(terminal.drain, return_exceptions=True)
            self.items.pop(identifier, None)
        return ReleaseTerminalResponse()

    async def close(self):
        results = await asyncio.gather(*(self.release(key) for key in tuple(self.items)), return_exceptions=True)
        for result in results:
            if isinstance(result, BaseException):
                raise result
