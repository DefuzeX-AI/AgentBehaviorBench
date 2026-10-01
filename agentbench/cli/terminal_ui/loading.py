"""A temporary loading line for synchronous CLI preparation."""

from __future__ import annotations

import shutil
import sys
from builtins import print as builtin_print
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from threading import Event, Thread


@contextmanager
def loading_line(label: str, output_fn: Callable[[str], None] = print) -> Iterator[None]:
    """Animate preparation on a terminal, then erase it even on interruption."""
    stream = sys.stdout
    if output_fn is not builtin_print or not stream.isatty():
        yield
        return

    # Leave one column free so the line does not wrap in a narrow terminal.
    width = max(1, shutil.get_terminal_size((80, 24)).columns - 1)
    frames = tuple(f"  {label}{dots:<3}"[:width] for dots in (".", "..", "..."))
    stopped = Event()

    def render(frame: str) -> None:
        stream.write("\r" + frame)
        stream.flush()

    def animate() -> None:
        index = 1
        while not stopped.wait(0.35):
            render(frames[index % len(frames)])
            index += 1

    render(frames[0])
    thread = Thread(target=animate, daemon=True, name="agentbench-loading")
    thread.start()
    try:
        yield
    finally:
        stopped.set()
        thread.join()
        render(" " * len(frames[0]))
        stream.write("\r")
        stream.flush()
