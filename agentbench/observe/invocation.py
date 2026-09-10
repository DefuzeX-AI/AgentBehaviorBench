"""Shared live observation lifecycle, independent of runtime and SDK."""
from pathlib import Path
from .store import TraceStore, atomic_json
from .observers import DEFAULT_OBSERVERS


class InvocationObservation:
    def __init__(self, directory, invocation_id, session_id, framework, *, context=None, provider=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = TraceStore(self.directory / 'framework.jsonl', session_id, source='framework', context=context)
        try:
            from .otel.session import ObservedStore
        except ModuleNotFoundError as exc:
            if not (exc.name or '').startswith('opentelemetry'):
                raise
            atomic_json(self.directory / 'otel-status.json', {'status': 'unavailable', 'reason': 'OTel SDK not installed'})
        else:
            self.store = ObservedStore(self.store, invocation_id, provider=provider)
        self.callbacks = DEFAULT_OBSERVERS.callbacks(framework, self.store)

    def config(self, value=None):
        # Do not deepcopy user callback objects (may own locks/resources).
        config = dict(value or {})
        callbacks = config.get('callbacks')
        if callbacks is None or isinstance(callbacks, (list, tuple)):
            config['callbacks'] = list(callbacks or ()) + self.callbacks
        else:
            callbacks = callbacks.copy()
            for handler in self.callbacks:
                callbacks.add_handler(handler)
            config['callbacks'] = callbacks
        return config

    def close(self):
        if hasattr(self.store, 'close'):
            self.store.close()
