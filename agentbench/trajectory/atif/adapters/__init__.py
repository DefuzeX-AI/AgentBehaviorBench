"""Explicit strategy selection; no Agent-name detection."""
from .deepagents import DeepAgentsAdapter
from .opencode import OpenCodeAdapter


def selected(names):
    factories = {"deepagents": DeepAgentsAdapter, "opencode": OpenCodeAdapter}
    unknown = set(names) - factories.keys()
    if unknown:
        raise ValueError("Unknown delegation adapters: " + ", ".join(sorted(unknown)))
    return [factories[name]() for name in dict.fromkeys(names)]
