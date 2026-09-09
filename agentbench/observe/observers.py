"""Independent observer selection; runtime and framework execution stay separate."""
from collections.abc import Callable


class ObserverFactory:
    def __init__(self):
        self._builders: dict[str, Callable] = {}

    def register(self, name, builder):
        if name in self._builders:
            raise ValueError(f"Observer already registered: {name}")
        self._builders[name] = builder

    def callbacks(self, framework, store):
        builder = self._builders.get(framework)
        return [] if builder is None else [builder(store)]


def _langchain(store):
    from .langchain import TraceCallback
    return TraceCallback(store)


DEFAULT_OBSERVERS = ObserverFactory()
DEFAULT_OBSERVERS.register("langgraph", _langchain)
