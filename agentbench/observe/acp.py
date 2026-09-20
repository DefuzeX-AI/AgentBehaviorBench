"""Live ACP evidence projection; never reconstruct imaginary internal LLM spans."""
from uuid import uuid4
from .store import TraceStore, atomic_json, redact


class ACPObserver:
    def __init__(self, store):
        self.store = store
        self.directory = store.path.parent
        base = getattr(store, 'store', store)
        self.events = TraceStore(self.directory / 'acp-events.jsonl', store.run_id,
                                 source='acp', context=base.context)
        self.secrets = base._secrets
        self.tools = {}
        self.prefix = uuid4().hex
        self.summary = {'coverage': 'protocol_events', 'internal_model_spans': 'not_observed',
                        'tool_calls': 0, 'incomplete_tools': []}

    def on_acp_event(self, name, data):
        self.events.record(name, **data)
        # Stream chunks and tool updates remain in full local payloads. Tool
        # lifecycle/content gets its own spans below; duplicating every update
        # on the root span exhausts bounded OTel/SDK event buffers.
        self.store.record('native_event', name='acp.' + name, payload=data,
                          span_event=name != 'session_update')
        if name in ('initialize', 'session', 'prompt_completed', 'failure'):
            self.summary[name] = data
        if name == 'stderr_truncated':
            self.summary['stderr_truncated'] = True
        if name == 'session_update':
            update = data['update']
            if update.get('sessionUpdate') in ('tool_call', 'tool_call_update'):
                self._tool(update)
        self.summary['incomplete_tools'] = [key for key, state in self.tools.items() if not state['ended']]
        atomic_json(self.directory / 'acp-summary.json', redact(self.summary, self.secrets))

    def _tool(self, update):
        identifier = update['toolCallId']
        state = self.tools.get(identifier)
        if state is None:
            state = self.tools[identifier] = {'fields': {}, 'started': False, 'ended': False,
                                             'span': f'{self.prefix}:{identifier}'}
        state['fields'].update({k: v for k, v in update.items() if v is not None})
        fields = state['fields']
        # A progress message without a start remains evidence, not a fabricated start.
        if update['sessionUpdate'] == 'tool_call' and not state['started']:
            state['started'] = True
            self.summary['tool_calls'] += 1
            inputs = {'input': fields['rawInput']} if 'rawInput' in fields else {}
            self.store.record('span_start', kind='tool', span_id=state['span'],
                name=fields.get('title', 'ACP tool'), tool_call_id=identifier, **inputs)
        if not state['started'] or state['ended']:
            return
        if 'rawInput' in update:
            self.store.record('span_update', span_id=state['span'], input=update['rawInput'])
        if fields.get('status') in ('completed', 'failed'):
            state['ended'] = True
            result = ({'output': fields['rawOutput']} if 'rawOutput' in fields else
                      {'output': fields['content']} if 'content' in fields else {})
            self.store.record('span_end', span_id=state['span'], tool_call_id=identifier,
                tool_status='error' if fields['status'] == 'failed' else 'succeeded', **result)
