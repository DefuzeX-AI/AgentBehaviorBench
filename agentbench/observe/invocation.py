"""Shared live observation lifecycle, independent of runtime and SDK."""
from pathlib import Path
from .store import TraceStore
from .observers import DEFAULT_OBSERVERS


class InvocationObservation:
    def __init__(self, directory, session_id, framework, *, context=None):
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.store = TraceStore(self.directory / 'framework.jsonl', session_id, source='framework', context=context)
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
