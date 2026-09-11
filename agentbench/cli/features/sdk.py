"""Inspect evaluation SDKs available to the CLI."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.plugins import (
    SDK_ENTRY_POINT_GROUP,
    installed_sdk_references,
    plugin_execution,
    resolve_sdk,
)

from .base import CommandFeature


def configure_parser(parser: ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="sdk_command", required=True)
    list_parser = commands.add_parser(
        "list", help="List built-in and installed evaluation SDKs."
    )
    list_parser.set_defaults(sdk_handler=_list_sdks)
    show_parser = commands.add_parser(
        "show", help="Load one SDK and show its execution interface."
    )
    show_parser.add_argument("name", help="SDK NAME or DISTRIBUTION::NAME.")
    show_parser.set_defaults(sdk_handler=_show_sdk)


def execute(args: Namespace) -> int:
    handler = getattr(args, "sdk_handler", None)
    if not callable(handler):
        raise RuntimeError("No SDK command handler registered")
    try:
        return handler(args)
    except ProviderSelectionError as exc:
        print(f"SDK configuration error: {exc}")
        return 2


def _list_sdks(args: Namespace) -> int:
    del args
    print("NAME\tSOURCE\tDISTRIBUTION\tVERSION\tOBJECT")
    for reference in installed_sdk_references():
        print(
            "\t".join(
                (
                    reference.name,
                    reference.source,
                    reference.distribution or "-",
                    reference.version or "-",
                    reference.object_ref,
                )
            )
        )
    print(f"Entry point group: {SDK_ENTRY_POINT_GROUP}")
    return 0


def _show_sdk(args: Namespace) -> int:
    selection = resolve_sdk(args.name)
    reference = selection.reference
    print(f"Name: {reference.name}")
    print(f"Source: {reference.source}")
    print(f"Distribution: {reference.distribution or '-'}")
    print(f"Version: {reference.version or '-'}")
    print(f"Object: {reference.object_ref}")
    print(f"Execution: {plugin_execution(selection.value)}")
    return 0


FEATURE = CommandFeature(
    name="sdk",
    help="List and inspect evaluation SDK plugins.",
    description=(
        "Discover SDK plugins installed through Python package entry points, "
        "without importing them during listing."
    ),
    configure=configure_parser,
    execute=execute,
)
