"""Step sources: which recorded evidence becomes the model and tool steps.

An attempt has one source, chosen from the Agent unit frozen in
``request/target.json``: ``[atif] source`` when the unit declares one, else the
default of its ``[adapter] type``. Without a frozen adapter type, the framework
recorded in the invocation requests decides. Nothing is detected from an
Agent's name. A format that needs its own reading adds a module here and
registers it below.
"""
from .acp_otel import AcpOtelSource
from .langgraph import LangGraphSource

_FACTORIES = {"langgraph": LangGraphSource, "acp_otel": AcpOtelSource}
# [adapter] type -> source. An attempt that recorded no adapter type at all
# predates these records and is read from its framework records.
_DEFAULTS = {"langgraph": "langgraph", "acp": "acp_otel", None: "langgraph"}
SOURCE_NAMES = tuple(_FACTORIES)


def declared(target, inputs=()):
    """The source name the recorded attempt selects."""
    runtime = target.get("runtime") or {}
    name = (runtime.get("atif") or {}).get("source")
    if name is not None:
        return name
    adapter = (runtime.get("adapter") or {}).get("type")
    if adapter is None:
        # A standalone observe run freezes no target; each invocation request names its framework.
        recorded = {(item.get("request") or {}).get("framework") for item in inputs} - {None}
        adapter = recorded.pop() if len(recorded) == 1 else None
    if adapter not in _DEFAULTS:
        raise ValueError(f"No ATIF step source for adapter type {adapter!r}; declare [atif] source in agent.toml")
    return _DEFAULTS[adapter]


def select(name):
    if name not in _FACTORIES:
        raise ValueError(f"Unknown ATIF step source {name!r}; available: " + ", ".join(SOURCE_NAMES))
    return _FACTORIES[name]()
