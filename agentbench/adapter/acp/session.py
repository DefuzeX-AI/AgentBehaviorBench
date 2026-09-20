"""One ACP connection and native Agent session for a single Case attempt."""
import asyncio
import codecs
import os
from acp import PROTOCOL_VERSION, connect_to_agent, text_block
from acp.schema import ClientCapabilities, FileSystemCapabilities, Implementation
from .client import ACPClient, plain
from .errors import ACPError
from .process import child_environment, terminate_group


class ACPSession:
    def __init__(self, config):
        self.config = config
        self.process = self.conn = self.drain_task = None
        self.client = ACPClient(config, self.emit)
        self.callbacks = []
        self.busy = self.closed = False
        self.info = {}
        self._close_lock = asyncio.Lock()

    def emit(self, name, data):
        for callback in self.callbacks:
            callback.on_acp_event(name, data)

    async def start(self):
        self.process = await asyncio.create_subprocess_exec(
            *self.config.command, cwd=self.config.cwd, env=child_environment(self.config),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, limit=self.config.max_output_bytes,
            start_new_session=os.name == 'posix')
        self.drain_task = asyncio.create_task(self.drain_stderr())
        self.conn = connect_to_agent(self.client, self.process.stdin, self.process.stdout)
        initialized = await self.conn.initialize(
            protocol_version=PROTOCOL_VERSION, client_capabilities=ClientCapabilities(
                fs=FileSystemCapabilities(read_text_file=True, write_text_file=True), terminal=True),
            client_info=Implementation(name='agentbench', version='0.1.0'))
        if initialized.protocol_version != PROTOCOL_VERSION:
            raise ACPError('Unsupported ACP protocol version', phase='initialize')
        self.info = {'initialize': plain(initialized), 'pid': self.process.pid}
        self.emit('initialize', self.info)
        if self.config.auth_method:
            advertised = {item.id for item in initialized.auth_methods or []}
            if self.config.auth_method not in advertised:
                raise ACPError('Configured authentication method is not advertised', code='auth_required')
            await self.conn.authenticate(method_id=self.config.auth_method)
        session = await self.conn.new_session(cwd=self.config.cwd, mcp_servers=[])
        await self.client.bind_session(session.session_id)
        self.info['session'] = plain(session)
        self.emit('session', self.info['session'])

    async def drain_stderr(self):
        decoder = codecs.getincrementaldecoder('utf-8')(errors='replace')
        written = 0
        while chunk := await self.process.stderr.read(8192):
            if written < self.config.max_output_bytes:
                kept = chunk[:self.config.max_output_bytes - written]
                self.emit('stderr', {'text': decoder.decode(kept)})
            if written <= self.config.max_output_bytes < written + len(chunk):
                self.emit('stderr_truncated', {'limit': self.config.max_output_bytes})
            written += len(chunk)

    async def invoke(self, text, callbacks):
        if self.closed:
            raise ACPError('ACP session is closed', code='session_closed')
        if self.busy:
            raise ACPError('A prompt is already active for this Case', code='concurrent_prompt')
        self.busy = True
        self.callbacks = callbacks
        self.client.parts, self.client.output_bytes, self.client.error = [], 0, None
        try:
            if self.conn is None:
                await asyncio.wait_for(self.start(), min(self.config.handshake_timeout, self.config.timeout))
            self.emit('prompt_started', {'session_id': self.client.session_id, 'input': text})
            response = await asyncio.wait_for(self.conn.prompt(
                session_id=self.client.session_id, prompt=[text_block(text)]), self.config.timeout)
            if self.client.error:
                raise self.client.error
            if self.drain_task.done() and self.drain_task.exception():
                raise self.drain_task.exception()
            self.emit('prompt_completed', plain(response))
            stop = response.stop_reason
            if stop == 'cancelled':
                raise asyncio.CancelledError('ACP Agent cancelled the prompt')
            if stop not in ('end_turn', 'refusal'):
                raise ACPError(f'ACP stopped before completion: {stop}', code=stop)
            return ''.join(self.client.parts), {**self.info, 'session_id': self.client.session_id,
                    'stop_reason': stop, 'prompt_response': plain(response)}
        except BaseException as exc:
            try:
                self.emit('failure', {'type': type(exc).__name__, 'message': str(exc),
                                      'code': getattr(exc, 'code', None)})
            finally:
                await self.close()
            raise
        finally:
            self.callbacks = []
            self.busy = False

    async def close(self):
        async with self._close_lock:
            if self.closed:
                return
            self.closed = True
            try:
                if self.conn and self.busy and self.client.session_id:
                    try:
                        await asyncio.wait_for(self.conn.cancel(session_id=self.client.session_id),
                                               self.config.cleanup_timeout)
                    except (Exception, asyncio.CancelledError):
                        pass
            finally:
                try:
                    try:
                        await terminate_group(self.process, self.config.cleanup_timeout)
                    finally:
                        await self.client.terminals.close()
                finally:
                    if self.conn:
                        try:
                            await asyncio.wait_for(self.conn.close(), self.config.cleanup_timeout)
                        except (Exception, asyncio.CancelledError):
                            pass
                    if self.drain_task:
                        self.drain_task.cancel()
                        await asyncio.gather(self.drain_task, return_exceptions=True)
