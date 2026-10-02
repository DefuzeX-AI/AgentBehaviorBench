"""Viewer requests use the same durable reuse queue as CLI requests."""

from .reuse import execute_reuse


def execute_reuse_command(source, *, command_id, selection, environ, on_created=None,
                          run_control=None, on_runner=None):
    return execute_reuse(source, command_id=command_id, selection=selection, environ=environ,
        on_created=on_created, run_control=run_control, on_runner=on_runner).directory
