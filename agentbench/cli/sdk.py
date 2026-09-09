"""Load a user-selected SDK without interpreting its configuration."""

from __future__ import annotations

import importlib
import json
from argparse import ArgumentParser, Namespace
from pathlib import Path

from agentbench.harness.errors import ProviderSelectionError


def configure_sdk_parser(parser: ArgumentParser) -> None:
    parser.add_argument(
        "--sdk",
        metavar="MODULE[:OBJECT]",
        help="Import a module or configured object exposing create_run().",
    )
    parser.add_argument(
        "--sdk-options",
        metavar="PATH",
        help="JSON object of options passed to the selected SDK.",
    )


def sdk_arguments(args: Namespace) -> dict[str, object]:
    result: dict[str, object] = {}
    if args.sdk is not None:
        module_name, separator, attribute = args.sdk.partition(":")
        if not module_name or (separator and not attribute):
            raise ProviderSelectionError("--sdk must use MODULE or MODULE:OBJECT")
        try:
            sdk = importlib.import_module(module_name)
            if separator:
                sdk = getattr(sdk, attribute)
        except (ImportError, AttributeError) as exc:
            raise ProviderSelectionError("Could not import the selected SDK") from exc
        if isinstance(sdk, type) or not callable(getattr(sdk, "create_run", None)):
            raise ProviderSelectionError(
                "SDK must be a module or object with create_run()"
            )
        result["sdk"] = sdk
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
    return result
