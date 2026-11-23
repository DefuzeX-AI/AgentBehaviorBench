"""Shared CLI options whose meaning is the same in every command."""

from __future__ import annotations

from argparse import ArgumentParser, ArgumentTypeError
from pathlib import Path

ENV_FILE_HELP = "Load host secrets and defaults from PATH instead of .env."
MODEL_HELP = "Target model ID; defaults to the selected provider model environment variable."


def model_name(value: str) -> str:
    """Reject an Agent number given where a model name belongs."""
    if value.strip().isdecimal():
        raise ArgumentTypeError(
            f"--model expects a model name, not an Agent number ({value.strip()}); "
            "select Agents with the command's own Agent argument"
        )
    return value


def configure_env_file(parser: ArgumentParser, *, help: str = ENV_FILE_HELP) -> None:
    parser.add_argument("--env-file", type=Path, metavar="PATH", help=help)


def configure_model(parser: ArgumentParser, *, help: str = MODEL_HELP) -> None:
    parser.add_argument("--model", type=model_name, metavar="MODEL", help=help)
