"""Explicit strategy selection; no Agent-name detection."""
from .deepagents import DeepAgentsAdapter
from .openclaw import OpenClawAdapter
from .opencode import OpenCodeAdapter


_FACTORIES = {"deepagents": DeepAgentsAdapter, "opencode": OpenCodeAdapter, "openclaw": OpenClawAdapter}
ADAPTER_NAMES = tuple(_FACTORIES)


def selected(names):
    unknown = set(names) - _FACTORIES.keys()
    if unknown:
        raise ValueError("Unknown delegation adapters: " + ", ".join(sorted(unknown)))
    return [_FACTORIES[name]() for name in dict.fromkeys(names)]
