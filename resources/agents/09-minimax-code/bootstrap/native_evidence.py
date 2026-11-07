"""Read MiniMax's opt-in native LLM Context Inspector without copying payloads.

Pinned native implementation drains successful main-agent captures before the
ACP prompt completes. It excludes title/auxiliary and failed attempts. The
adapter reads each native call once at that boundary; it does not use clocks.
"""
import base64
import json
import os
from pathlib import Path


def read_json(path, root, maximum=16 * 1024 * 1024):
    if any(p.is_symlink() for p in (path, *path.parents) if p.is_relative_to(root)):
        raise ValueError('Native evidence contains a linked path')
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or resolved.stat().st_size > maximum:
        raise ValueError('Native evidence is outside its boundary or too large')
    return json.loads(resolved.read_text())


def read_calls(session_id):
    root = Path(os.environ['MINIMAX_DATA_DIR'])
    found = []
    for manifest in root.glob('abb-byok-*/v2/sessions/**/manifest.json'):
        identity = read_json(manifest, root, 65536)
        if identity.get('sessionId') != session_id:
            continue
        folder = manifest.parent / 'llm-context-inspector'
        events = folder / 'events.jsonl'
        if not events.exists():
            continue
        if events.is_symlink() or events.stat().st_size > 8 * 1024 * 1024:
            raise ValueError('Native event stream exceeds its boundary')
        for line in events.read_text().splitlines():
            item = json.loads(line)
            if item.get('type') != 'call.captured' or item.get('v') != 1:
                continue
            call = item['callId']
            name = base64.urlsafe_b64encode(call.encode()).decode().rstrip('=')
            response_id = None
            if item.get('responseState') == 'AVAILABLE':
                response = read_json(folder / 'payloads' / (name + '.response.json'), root)
                response_id = response.get('id')
            found.append({'native_call_id': call, 'native_turn_id': item['turnId'],
                'native_session_id': session_id, 'native_response_id': response_id,
                'purpose': 'agent', 'attempt_count': item['attemptCount'],
                'capture_status': item.get('responseState'),
                'source_contract': 'minimax.llm-context-inspector.v1'})
    return found
