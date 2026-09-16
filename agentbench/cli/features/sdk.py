"""Inspect evaluation SDKs available to the CLI."""

from __future__ import annotations

from argparse import ArgumentParser, Namespace

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.discovery import discover_sdks
from agentbench.sdk.plugins import plugin_execution, resolve_sdk

from .base import CommandFeature


def configure_parser(parser: ArgumentParser) -> None:
    commands = parser.add_subparsers(dest="sdk_command", required=True)
    list_parser = commands.add_parser(
        "list", help="List evaluation adapters found in the SDK directory."
    )
    list_parser.set_defaults(sdk_handler=_list_sdks)
    show_parser = commands.add_parser(
        "show", help="Load one SDK and show its execution interface."
    )
    show_parser.add_argument("name", help="SDK adapter directory name.")
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
    references = discover_sdks()
    print("NAME\tSOURCE\tOBJECT")
    for reference in references:
        print(f"{reference.name}\t{reference.source}\t{reference.object_ref}")
    if not references:
        print("No SDK adapters found under agentbench/sdk/plugin/.")
    else:
        print("Discovered adapters only; SDK dependencies are checked before execution.")
    return 0


def _show_sdk(args: Namespace) -> int:
    selection = resolve_sdk(args.name)
    reference = selection.reference
    print(f"Name: {reference.name}")
    print(f"Source: {reference.source}")
    print(f"Object: {reference.object_ref}")
    print(f"Execution: {plugin_execution(selection.value)}")
    return 0


FEATURE = CommandFeature(
    name="sdk",
    help="List and inspect evaluation SDK plugins.",
    description=(
        "Discover adapter packages under agentbench/sdk/plugin/, "
        "without importing them during listing."
    ),
    configure=configure_parser,
    execute=execute,
)
