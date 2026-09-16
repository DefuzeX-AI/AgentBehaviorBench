"""Find SDK adapters in this package without importing their implementations."""

from __future__ import annotations

import importlib
import keyword
from pathlib import Path

from agentbench.harness.errors import ProviderSelectionError

from .contracts import SDKReference


SDK_ROOT = Path(__file__).resolve().parent / "plugin"


def discover_sdks() -> tuple[SDKReference, ...]:
    """List direct child packages containing a ``plugin.py`` entry module.

    Only sdk/plugin/ is scanned, relative to this installed package rather than
    the working directory. Sibling packages under sdk/ are not candidates.
    Helper/private directories are ignored. Candidate packages must have a
    valid Python identifier, an ``__init__.py``, and no linked entry paths.
    Names are compared case-insensitively and returned in deterministic order.
    No SDK imports, dependency checks, network calls, or execution occur here.

    Raises:
        ProviderSelectionError: If the directory cannot be read, an adapter
            package is malformed, or two names differ only by letter case.
    """
    references: dict[str, SDKReference] = {}
    try:
        for directory in sorted(SDK_ROOT.iterdir(), key=lambda p: p.name):
            if directory.name.startswith(("_", ".")) or not directory.is_dir():
                continue
            entry = directory / "plugin.py"
            if not entry.is_file():
                continue
            name = directory.name
            if not name.isascii() or not name.isidentifier() or keyword.iskeyword(name):
                raise ProviderSelectionError(f"Invalid SDK directory name: {name!r}")
            initializer = directory / "__init__.py"
            if not initializer.is_file():
                raise ProviderSelectionError(f"SDK {name!r} is missing __init__.py")
            if (
                directory.is_symlink()
                or directory.resolve() != SDK_ROOT.resolve() / name
                or entry.is_symlink()
                or initializer.is_symlink()
            ):
                raise ProviderSelectionError(
                    f"SDK {name!r} must use unlinked package files"
                )
            key = name.casefold()
            if key in references:
                raise ProviderSelectionError(f"Duplicate SDK directory name: {name!r}")
            references[key] = SDKReference(
                name=name,
                source="directory",
                object_ref=f"{__package__}.plugin.{name}.plugin:plugin",
            )
    except OSError as exc:
        raise ProviderSelectionError(
            "Could not read the SDK adapter directory"
        ) from exc
    return tuple(references[key] for key in sorted(references))


def load_sdk(reference: SDKReference) -> object:
    """Import only the selected entry module and retrieve its ``plugin`` instance.

    Callers must use a reference produced by ``discover_sdks``. Python's normal
    module cache applies; restarting the process is required after editing an
    already loaded adapter. Dependency and entry errors retain their cause.
    """
    module_name, _, attribute = reference.object_ref.partition(":")
    try:
        # import agentbench.sdk.plugin.kuma.plugin
        module = importlib.import_module(module_name)
        return getattr(module, attribute)



    except ModuleNotFoundError as exc:
        raise ProviderSelectionError(
            f"Could not load SDK {reference.name!r}: missing module {exc.name!r}. "
            "Install its dependencies in the appropriate execution environment "
            "and keep plugin.py imports lightweight."
        ) from exc
    except Exception as exc:
        raise ProviderSelectionError(
            f"Could not load SDK {reference.name!r} from {reference.object_ref} "
            f"({type(exc).__name__}); check its plugin export."
        ) from exc
