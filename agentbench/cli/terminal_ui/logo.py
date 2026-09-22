"""Terminal branding for the AgentBench command line interface."""

from __future__ import annotations

from collections.abc import Callable

from .constants import (
    ANSI_BLUE,
    ANSI_BOLD,
    ANSI_CYAN,
    ANSI_MAGENTA,
    ANSI_RESET,
    ANSI_YELLOW,
)


BBA_LOGO = "\n".join(
    (
        f"{ANSI_CYAN}+------------------------------------------------------------------------------+{ANSI_RESET}",
        f"{ANSI_YELLOW}|   *       .       *       .       *       .       *       .       *       .  |{ANSI_RESET}",
        f"{ANSI_YELLOW}|         .       *       .       *       .       *       .       *       .    |{ANSI_RESET}",
        f"{ANSI_CYAN}|                                                                              |{ANSI_RESET}",
        f"{ANSI_MAGENTA}{ANSI_BOLD}|                              ____  ____    _                                 |{ANSI_RESET}",
        f"{ANSI_BLUE}{ANSI_BOLD}|                             | __ )| __ )  / \\                                |{ANSI_RESET}",
        f"{ANSI_CYAN}{ANSI_BOLD}|                             |  _ \\|  _ \\ / _ \\                               |{ANSI_RESET}",
        f"{ANSI_YELLOW}{ANSI_BOLD}|                             | |_) | |_) / ___ \\                              |{ANSI_RESET}",
        f"{ANSI_MAGENTA}{ANSI_BOLD}|                             |____/|____/_/   \\_\\                             |{ANSI_RESET}",
        f"{ANSI_CYAN}|                                                                              |{ANSI_RESET}",
        f"{ANSI_YELLOW}|                             Agent Behavior Bench                             |{ANSI_RESET}",
        f"{ANSI_YELLOW}|         *       .       *       .       *       .       *       .       *    |{ANSI_RESET}",
        f"{ANSI_CYAN}+------------------------------------------------------------------------------+{ANSI_RESET}",
    )
)


def print_logo(output_fn: Callable[[str], None] = print) -> None:
    """Write the BBA terminal logo through the selected output function."""

    output_fn(BBA_LOGO)
