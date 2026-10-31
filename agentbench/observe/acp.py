"""Live ACP evidence projection; never reconstruct imaginary internal LLM spans."""
from uuid import uuid4
from .store import TraceStore, atomic_json, redact
from .acp_evidence import TerminalSnapshots, ToolEvidence


class ACPObserver:
    def __init__(self, store):
        self.store = store
        self.directory = store.path.parent
        base = getattr(store, 'store', store)
        self.events = TraceStore(self.directory / 'acp-events.jsonl', store.run_id,
                                 source='acp', context=base.context)
        self.secrets = base._secrets
        self.tools = {}
        self.terminals = TerminalSnapshots(self.secrets)
        self.prefix = uuid4().hex
        self.summary = {'coverage': 'protocol_events', 'internal_model_spans': 'not_observed',
                        'tool_calls': 0, 'incomplete_tools': []}

    def add_secrets(self, secrets):
        values = tuple(value for value in secrets if isinstance(value, str) and value)
        if not values:
            return
        self.secrets = tuple(dict.fromkeys((*self.secrets, *values)))
        self.events.add_secrets(values)
        self.terminals.secrets = self.secrets

    def on_acp_event(self, name, data):
        self.events.record(name, **data)
        self.terminals.on_event(name, data)
        if name == 'native_model_call':
            self.store.record('native_model_call', **data, span_event=False)
        # Stream chunks and tool updates remain in full local payloads. Tool
        # lifecycle/content gets its own spans below; duplicating every update
        # on the root span exhausts bounded OTel/SDK event buffers.
        self.store.record('native_event', name='acp.' + name, payload=data,
                          span_event=name not in ('session_update', 'terminal_started', 'terminal_output',
                                                 'terminal_exited', 'terminal_released'))
        if name in ('initialize', 'session', 'prompt_completed', 'failure'):
            self.summary[name] = data
        if name == 'stderr_truncated':
            self.summary['stderr_truncated'] = True
        if name == 'session_update':
            update = data['update']
            if update.get('sessionUpdate') in ('tool_call', 'tool_call_update'):
                self._tool(update)
        if name in ('prompt_completed', 'failure'):
            # The prompt boundary ends observation, not the native tool outcome.
            # Preserve the missing outcome explicitly rather than fabricating success.
            for state in self.tools.values():
                if state['started'] and not state['ended'] and state['fields'].get('status') in ('completed', 'failed'):
                    self._finish(state)
                if state['started'] and not state['ended']:
                    state.update(ended=True, boundary_closed=True)
                    self.store.record('span_control', span_id=state['span'],
                                      control='acp_outcome_not_observed')
        self.summary['incomplete_tools'] = [key for key, state in self.tools.items()
                                          if not state['ended'] or state.get('boundary_closed')]
        atomic_json(self.directory / 'acp-summary.json', redact(self.summary, self.secrets))

    def _tool(self, update):
        identifier = update['toolCallId']
        state = self.tools.get(identifier)
        if state is None:
            state = self.tools[identifier] = {'fields': {}, 'started': False, 'ended': False,
                                             'span': f'{self.prefix}:{identifier}',
                                             'evidence': ToolEvidence(self.terminals, secrets=self.secrets)}
        state['evidence'].on_update(update)
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
        # Terminal output may continue until release, even after the tool's final
        # status. Resolve terminal-backed calls at the prompt boundary.
        if fields.get('status') in ('completed', 'failed') and not state['evidence'].identifiers(fields):
            self._finish(state)

    def _finish(self, state):
        state['ended'] = True
        fields = state['fields']
        self.store.record('span_end', span_id=state['span'], tool_call_id=fields['toolCallId'],
            tool_status='error' if fields['status'] == 'failed' else 'succeeded',
            **state['evidence'].result(fields))
