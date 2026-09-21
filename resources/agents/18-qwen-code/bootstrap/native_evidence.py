"""Qwen 0.24.2 native chat-record evidence, selected by ACP branch checkpoint.

Normal end_turn awaits recordBranchCheckpointTransaction (flush + strict append)
and returns its UUID in _meta['qwen.branchPoint']. Only that committed parent
chain is eligible; no polling, timestamps, text matching, or latest-file guess.
The existing logApiResponse path writes ui_telemetry even with telemetry and
usage statistics disabled. Only identifiers are exported, never chat payloads.
"""

import json
import os
from pathlib import Path
import re
import stat


PROFILE_ROOT = Path('/home/agent')
MAX_BYTES = 32 * 1024 * 1024
MAX_LINE_BYTES = 8 * 1024 * 1024
MAX_RECORDS = 100000
MAX_PROFILES = 128
CONTRACT = 'qwen-code.0.24.2.chat-record.ui-telemetry'


def _identifier(value):
    return isinstance(value, str) and re.fullmatch(r'[A-Za-z0-9_-]{1,128}', value) is not None


def _unlinked(path, root):
    """Reject links/junctions before opening a transcript or traversing a profile."""
    if not path.is_relative_to(root):
        raise ValueError('Native evidence is outside its profile boundary')
    for part in (path, *path.parents):
        if not part.is_relative_to(root):
            break
        if part.is_symlink() or getattr(part, 'is_junction', lambda: False)():
            raise ValueError('Native evidence contains a linked path')
    if not path.resolve().is_relative_to(root.resolve()):
        raise ValueError('Native evidence escapes its profile boundary')


def _transcript(root, session_id):
    matches = []
    for number, profile in enumerate(root.glob('abb-qwen-*')):
        if number >= MAX_PROFILES:
            raise ValueError('Too many native profiles to inspect')
        _unlinked(profile, root)
        if not profile.is_dir():
            continue
        projects = profile / 'projects'
        _unlinked(projects, root)
        if not projects.is_dir():
            continue
        for number, project in enumerate(projects.iterdir()):
            if number >= MAX_PROFILES:
                raise ValueError('Too many native projects to inspect')
            _unlinked(project, root)
            chats = project / 'chats'
            _unlinked(chats, root)
            candidate = chats / (session_id + '.jsonl')
            _unlinked(candidate, root)
            if candidate.exists():
                matches.append(candidate)
    if len(matches) != 1:
        raise ValueError('Native session transcript is missing or ambiguous')
    return matches[0]


def _records_through(path, root, session_id, checkpoint_id):
    _unlinked(path, root)
    info = path.stat()
    if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
        raise ValueError('Native transcript is not a bounded regular file')
    # O_NOFOLLOW closes the final-component link race on the Linux runtime.
    fd = os.open(path, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
    with os.fdopen(fd, 'rb') as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ValueError('Native transcript changed while opening')
        records, total = {}, 0
        while True:
            line = stream.readline(MAX_LINE_BYTES + 1)
            if not line:
                break
            total += len(line)
            if total > MAX_BYTES or len(line) > MAX_LINE_BYTES or len(records) >= MAX_RECORDS:
                raise ValueError('Native transcript exceeds the evidence budget')
            if not line.endswith(b'\n'):
                raise ValueError('Native checkpoint has not been completely written')
            try:
                record = json.loads(line)
            except (ValueError, UnicodeError):
                raise ValueError('Native transcript contains invalid JSON') from None
            if (not isinstance(record, dict) or record.get('sessionId') != session_id
                    or not _identifier(record.get('uuid'))):
                raise ValueError('Native transcript record identity is invalid')
            key = record['uuid']
            if key in records:
                raise ValueError('Native transcript contains duplicate record IDs')
            records[key] = record
            if key == checkpoint_id:
                return records  # Later asynchronous records belong to no inferred Input.
    raise ValueError('Native prompt checkpoint is absent from the transcript')


def _committed_segment(records, checkpoint_id, assistant_id):
    checkpoint = records[checkpoint_id]
    payload = checkpoint.get('systemPayload')
    if (checkpoint.get('type') != 'system' or checkpoint.get('subtype') != 'branch_checkpoint'
            or not isinstance(payload, dict) or type(payload.get('v')) is not int or payload['v'] != 1
            or payload.get('assistantRecordUuid') != assistant_id
            or 'startExclusiveRecordUuid' not in payload):
        raise ValueError('Native checkpoint does not match the ACP completion')
    start, current = payload['startExclusiveRecordUuid'], checkpoint.get('parentUuid')
    if start is not None and (not _identifier(start) or start not in records):
        raise ValueError('Native checkpoint start boundary is missing')
    chain, visited = [], {checkpoint_id}
    while current != start:
        if not _identifier(current) or current not in records or current in visited:
            raise ValueError('Native checkpoint parent chain is incomplete or cyclic')
        record = records[current]
        visited.add(current)
        chain.append(record)
        if 'parentUuid' not in record:
            raise ValueError('Native record has no parent boundary')
        current = record['parentUuid']
    if not any(r['uuid'] == assistant_id and r.get('type') == 'assistant' for r in chain):
        raise ValueError('Native checkpoint assistant record is outside this turn')
    return reversed(chain)


def read_calls(session_id, *, prompt_response):
    """Return this completed main turn's explicit native model-response IDs.

    Missing checkpoints, truncated logs or ambiguous identities raise rather
    than attributing a stale/late record to the current Input. Failed attempts,
    auxiliary work, subagents and completions without a checkpoint stay unlinked.
    """
    if not _identifier(session_id):
        raise ValueError('Invalid native session ID')
    if not isinstance(prompt_response, dict) or prompt_response.get('stopReason') != 'end_turn':
        raise ValueError('Native evidence requires a completed end_turn checkpoint')
    metadata = prompt_response.get('_meta')
    point = metadata.get('qwen.branchPoint') if isinstance(metadata, dict) else None
    if not isinstance(point, dict) or not all(_identifier(point.get(k)) for k in ('checkpointUuid', 'assistantRecordUuid')):
        raise ValueError('Native ACP completion has no committed branch checkpoint')
    root = PROFILE_ROOT
    records = _records_through(_transcript(root, session_id), root, session_id, point['checkpointUuid'])
    segment = _committed_segment(records, point['checkpointUuid'], point['assistantRecordUuid'])
    calls, turns, response_ids = [], set(), set()
    for record in segment:
        if record.get('type') != 'system' or record.get('subtype') != 'ui_telemetry':
            continue
        payload = record.get('systemPayload')
        event = payload.get('uiEvent') if isinstance(payload, dict) else None
        if not isinstance(event, dict) or event.get('event.name') != 'qwen-code.api_response':
            continue
        if (record.get('isSidechain') or record.get('agentId') or record.get('backgroundTurn')
                or event.get('subagent_id') or event.get('subagent_name') not in (None, 'main')):
            continue
        prompt_id, response_id = event.get('prompt_id'), event.get('response_id')
        if not isinstance(prompt_id, str) or not re.fullmatch(re.escape(session_id) + r'########[1-9][0-9]*', prompt_id):
            continue  # Native internal/side-query/subagent prompt IDs are not main turns.
        if (not isinstance(response_id, str) or not response_id.strip() or len(response_id) > 512
                or any(ord(c) < 32 or ord(c) == 127 for c in response_id)):
            continue  # The provider may omit an ID: never synthesize one.
        if response_id in response_ids:
            raise ValueError('Native turn contains duplicate model-response identities')
        response_ids.add(response_id)
        turns.add(prompt_id)
        calls.append({'native_call_id': record['uuid'], 'native_session_id': session_id,
                      'native_turn_id': prompt_id, 'native_response_id': response_id,
                      'native_checkpoint_id': point['checkpointUuid'], 'purpose': 'agent',
                      'capture_status': 'recorded', 'source_contract': CONTRACT})
    if len(turns) > 1:
        raise ValueError('Native checkpoint spans multiple main prompt identities')
    return calls
