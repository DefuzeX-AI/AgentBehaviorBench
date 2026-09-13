"""Resolve a CLI-selected SDK without interpreting its configuration."""

from __future__ import annotations

import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from agentbench.harness.errors import ProviderSelectionError
from agentbench.sdk.plugins import resolve_sdk


def configure_sdk_parser(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--sdk",
        metavar="NAME|DISTRIBUTION::NAME|python:MODULE[:OBJECT]",
        help=(
            "Select an installed SDK plugin by entry-point name. "
            "Use python:MODULE[:OBJECT] for host-side development imports."
        ),
    )
    parser.add_argument(
        "--sdk-options",
        metavar="PATH",
        help="JSON object of options passed to the selected SDK.",
    )
    parser.add_argument(
        "--sdk-source",
        metavar="PATH",
        type=Path,
        help="Override the selected SDK's sdk_source option.",
    )


def sdk_arguments(args: Namespace) -> dict[str, object]:
    result: dict[str, object] = {}
    if args.sdk is not None:
        result["sdk_selection"] = resolve_sdk(args.sdk)
    if args.sdk_options is not None:
        try:
            options = json.loads(Path(args.sdk_options).read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeError, ValueError) as exc:
            # Never echo JSON contents, which may contain private SDK settings.
            raise ProviderSelectionError(
                "Could not read SDK options as a JSON object"
            ) from exc
        if not isinstance(options, dict):
            raise ProviderSelectionError("SDK options must be a JSON object")
        result["sdk_options"] = options
    if getattr(args, "sdk_source", None) is not None:
        # A command-line value wins over the same key in --sdk-options.
        result["sdk_options"] = {**result.get("sdk_options", {}),
                                 "sdk_source": args.sdk_source}
    return result
