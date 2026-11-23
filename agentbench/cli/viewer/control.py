"""Bound local Viewer control validation, separate from HTTP rendering."""

import json
import secrets
from urllib.parse import urlparse

MAX_COMMAND_BYTES = 16 * 1024


def local_origin(headers, *, require_origin=False):
    """Validate the browser origin before revealing control capabilities."""
    host = headers.get('Host', '')
    origin = headers.get('Origin')
    try:
        allowed_host = urlparse(f'http://{host}').hostname in ('localhost', '127.0.0.1', '::1')
    except ValueError:
        return False
    return (allowed_host and (not require_origin or bool(origin))
            and (not origin or origin == f'http://{host}')
            and headers.get('Sec-Fetch-Site') != 'cross-site')


def bound_controller(result_log):
    """Resolve the registered coordinator; importing a log never starts a runner."""
    try:
        from agentbench.cli.sessions.control import get_control
    except ImportError:
        return None
    return get_control(result_log)


def capabilities(result_log):
    controller = bound_controller(result_log)
    return dict(controller.capabilities) if controller is not None else {'can_control': False}


def controlled_snapshot(snapshot, result_log):
    """Include queued and rejected commands even before a writer event is recorded."""
    controller = bound_controller(result_log)
    if controller is None:
        return {**snapshot, 'capabilities': {'can_control': False}}
    recorded = snapshot.get('commands') or []
    if isinstance(recorded, dict):
        recorded = list(recorded.values())
    commands = {item['command_id']: item for item in recorded if isinstance(item, dict) and item.get('command_id')}
    for command in getattr(controller, 'commands', []):
        commands[command['command_id']] = command
    return {**snapshot, 'capabilities': dict(controller.capabilities), 'commands': list(commands.values())}


def valid_token(controller, token):
    expected = controller.capabilities.get('control_token')
    return isinstance(token, str) and isinstance(expected, str) and secrets.compare_digest(token, expected)


def read_command(headers, stream):
    """Accept one bounded JSON object; never accept arbitrary shell arguments."""
    if headers.get('Transfer-Encoding'):
        raise ValueError('Transfer encoding is not supported')
    if headers.get('Content-Type', '').split(';', 1)[0].strip() != 'application/json':
        raise ValueError('Expected application/json')
    try:
        size = int(headers.get('Content-Length', ''))
    except ValueError as exc:
        raise ValueError('A valid Content-Length is required') from exc
    if not 0 < size <= MAX_COMMAND_BYTES:
        raise ValueError('Command body is empty or too large')
    try:
        payload = json.loads(stream.read(size))
    except (ValueError, UnicodeDecodeError) as exc:
        raise ValueError('Invalid JSON command') from exc
    if not isinstance(payload, dict):
        raise ValueError('Command must be a JSON object')
    return payload
