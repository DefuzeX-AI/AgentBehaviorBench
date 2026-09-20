"""ACP callbacks with bounded reply accumulation and explicit permission decisions."""
from acp import RequestError
from acp.schema import RequestPermissionResponse, AllowedOutcome, DeniedOutcome
from .errors import ACPError
from .terminal import Terminals


def plain(value):
    return value.model_dump(mode='json', by_alias=True, exclude_none=True) if hasattr(value, 'model_dump') else value


class ACPClient:
    def __init__(self, config, emit):
        self.config, self.emit = config, emit
        self.session_id = None
        self.parts = []
        self.output_bytes = 0
        self.error = None
        self.terminals = Terminals(config, emit)
        self.pending_updates = []
        self.pending_bytes = 0

    async def bind_session(self, session_id):
        self.session_id = session_id
        updates, self.pending_updates = self.pending_updates, []
        for received_id, update in updates:
            await self.session_update(received_id, update)

    def on_connect(self, conn):
        self.conn = conn

    def check_session(self, session_id):
        if session_id != self.session_id:
            raise RequestError.invalid_params({'message': 'Session does not belong to this Case'})

    async def session_update(self, session_id, update, **kwargs):
        try:
            if self.session_id is None:
                import json
                self.pending_bytes += len(json.dumps(plain(update)).encode('utf-8'))
                if self.pending_bytes > self.config.max_output_bytes:
                    raise ACPError('ACP startup updates exceed output limit', code='output_limit')
                self.pending_updates.append((session_id, update))
                return
            self.check_session(session_id)
            event = plain(update)
            self.emit('session_update', {'session_id': session_id, 'update': event})
            if event.get('sessionUpdate') == 'agent_message_chunk':
                content = event.get('content', {})
                if content.get('type') == 'text':
                    text = content['text']
                    self.output_bytes += len(text.encode('utf-8'))
                    if self.output_bytes > self.config.max_output_bytes:
                        raise ACPError('ACP reply exceeds configured output limit', code='output_limit')
                    self.parts.append(text)
        except Exception as exc:
            # Notification errors must fail the invocation, not disappear in SDK logs.
            self.error = exc

    async def request_permission(self, session_id, tool_call, options, **kwargs):
        self.check_session(session_id)
        selected = next((item for item in options if item.kind == 'allow_once'), None)
        outcome = (AllowedOutcome(outcome='selected', option_id=selected.option_id)
                   if self.config.permission_policy == 'allow_once' and selected else
                   DeniedOutcome(outcome='cancelled'))
        self.emit('permission', {'session_id': session_id, 'tool_call': plain(tool_call),
                                'options': [plain(x) for x in options], 'outcome': plain(outcome)})
        return RequestPermissionResponse(outcome=outcome)

    async def ext_method(self, method, params):
        raise RequestError.method_not_found(method)

    async def ext_notification(self, method, params):
        self.emit('extension', {'method': method, 'params': params})

    async def read_text_file(self, session_id, path, line=None, limit=None, **kwargs):
        from .filesystem import read_file
        self.check_session(session_id)
        result = read_file(self.config, path, line, limit)
        self.emit('file_read', {'path': path, 'line': line, 'limit': limit, 'content': result.content})
        return result

    async def write_text_file(self, session_id, path, content, **kwargs):
        from .filesystem import write_file
        self.check_session(session_id)
        result = write_file(self.config, path, content)
        self.emit('file_written', {'path': path, 'content': content})
        return result

    async def create_terminal(self, session_id, command, args=None, env=None, cwd=None,
                              output_byte_limit=None, **kwargs):
        self.check_session(session_id)
        return await self.terminals.create(command, args, env, cwd, output_byte_limit)

    async def terminal_output(self, session_id, terminal_id, **kwargs):
        self.check_session(session_id)
        result = await self.terminals.output(terminal_id)
        self.emit('terminal_output', {'terminal_id': terminal_id, **plain(result)})
        return result

    async def wait_for_terminal_exit(self, session_id, terminal_id, **kwargs):
        self.check_session(session_id)
        return await self.terminals.wait(terminal_id)

    async def kill_terminal(self, session_id, terminal_id, **kwargs):
        self.check_session(session_id)
        return await self.terminals.kill(terminal_id)

    async def release_terminal(self, session_id, terminal_id, **kwargs):
        self.check_session(session_id)
        return await self.terminals.release(terminal_id)
