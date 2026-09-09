"""Import a LangGraph object from an official file.py:attribute entrypoint."""

from __future__ import annotations

import importlib
import inspect
import sys
from contextlib import contextmanager
from pathlib import Path
from threading import Lock
from types import ModuleType
from typing import Any, Iterator, Protocol

from .config import LangGraphAdapterConfig


class InvokableGraph(Protocol):
    def invoke(self, input: object, config: object | None = None, **kwargs: Any) -> object:
        """Run the graph with one input."""
        ...


class LangGraphLoadError(RuntimeError):
    """Raised when a configured graph entrypoint cannot be loaded."""


_IMPORT_LOCK = Lock()


def load_graph(config: LangGraphAdapterConfig) -> InvokableGraph:
    """Load a graph from its file.py:attribute entrypoint."""
    source_path, attribute = _parse_entrypoint(config)
    entry_root = config.agent_root / "bindings" if config.binding else config.source_root
    import_root, module_name = _module_location(entry_root, source_path)

    with _IMPORT_LOCK, _temporary_sys_path(import_root):
        importlib.invalidate_caches()
        module = _import_module(module_name, source_path)

    graph = _resolve_attribute(module, attribute)
    if not callable(getattr(graph, "invoke", None)) and callable(graph):
        graph = _call_zero_argument_factory(graph, config.entrypoint)
    if not callable(getattr(graph, "invoke", None)):
        raise LangGraphLoadError(
            f"LangGraph entrypoint does not provide invoke(): {config.entrypoint}"
        )
    return graph


def _parse_entrypoint(config: LangGraphAdapterConfig) -> tuple[Path, str]:
    """Split entrypoint into Python file and attribute."""
    file_name, separator, attribute = (config.binding or config.entrypoint).rpartition(":")
    if not separator or not file_name.strip() or not attribute.strip():
        raise LangGraphLoadError(
            f"Entrypoint must use 'file.py:attribute': {config.entrypoint!r}"
        )

    entry_root = (config.agent_root / "bindings").resolve() if config.binding else config.source_root
    if not entry_root.is_relative_to(config.agent_root):
        raise LangGraphLoadError("Binding directory escapes agent unit")
    source_path = (entry_root / file_name).resolve()
    if not source_path.is_relative_to(entry_root):
        raise LangGraphLoadError(f"Entrypoint escapes agent directory: {file_name}")
    if source_path.suffix != ".py" or not source_path.is_file():
        raise LangGraphLoadError(f"Entrypoint Python file does not exist: {source_path}")
    return source_path, attribute


def _module_location(agent_root: Path, source_path: Path) -> tuple[Path, str]:
    """Turn a Python file path into an import path."""
    src_root = agent_root / "src"
    import_root = src_root if source_path.is_relative_to(src_root) else agent_root
    relative_module = source_path.relative_to(import_root).with_suffix("")
    return import_root, ".".join(relative_module.parts)


def _import_module(module_name: str, source_path: Path) -> ModuleType:
    """Import the module from the expected file."""
    existing = sys.modules.get(module_name)
    if existing is not None:
        existing_file = getattr(existing, "__file__", None)
        if existing_file and Path(existing_file).resolve() != source_path:
            raise LangGraphLoadError(
                f"Python module collision for {module_name!r}. "
                "Use an isolated execution mode for agents with overlapping packages."
            )

    try:
        module = importlib.import_module(module_name)
    except Exception as exc:
        raise LangGraphLoadError(f"Failed to import {source_path}: {exc}") from exc

    loaded_file = getattr(module, "__file__", None)
    if loaded_file is None or Path(loaded_file).resolve() != source_path:
        raise LangGraphLoadError(
            f"Imported {module_name!r} from the wrong location: {loaded_file}"
        )
    return module


def _resolve_attribute(module: ModuleType, attribute_path: str) -> object:
    """Get the graph object from the module."""
    value: object = module
    try:
        for part in attribute_path.split("."):
            value = getattr(value, part)
    except AttributeError as exc:
        raise LangGraphLoadError(
            f"Entrypoint attribute does not exist: {module.__name__}:{attribute_path}"
        ) from exc
    return value


def _call_zero_argument_factory(factory: object, entrypoint: str) -> object:
    """Call a graph factory with no arguments."""
    signature = inspect.signature(factory)
    required = [
        parameter
        for parameter in signature.parameters.values()
        if parameter.default is inspect.Parameter.empty
        and parameter.kind
        in {inspect.Parameter.POSITIONAL_ONLY, inspect.Parameter.POSITIONAL_OR_KEYWORD}
    ]
    if required:
        raise LangGraphLoadError(
            f"Graph factory requires arguments and cannot run in-process: {entrypoint}"
        )
    try:
        return factory()  # type: ignore[operator]
    except Exception as exc:
        raise LangGraphLoadError(f"Graph factory failed: {entrypoint}: {exc}") from exc


@contextmanager
def _temporary_sys_path(path: Path) -> Iterator[None]:
    """Add one import path for a short time."""
    value = str(path)
    sys.path.insert(0, value)
    try:
        yield
    finally:
        try:
            sys.path.remove(value)
        except ValueError:
            pass
