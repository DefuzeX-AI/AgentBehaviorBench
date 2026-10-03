"""Fulfil model requests for existing source without executing it or reading secrets."""
import codecs
import json
import re

from ..common.responses import validate_response
from ..common.writer import save_json
from .context import safe_file
from .privacy import contains_secret, redact

PATH = re.compile(r'(?<![\w.])(?:[\w.-]+/)*[\w.-]+\.(?:py|ts|js|mjs|json|toml|yaml|yml|md|sql)(?![\w.])')


def add_source_files(session, paths):
    """Extend bounded, redacted context with exact safe paths; return changed paths."""
    files = session.context['files']
    requested = []
    for name in dict.fromkeys(paths):
        if not isinstance(name, str):
            continue
        name = name.removeprefix('agent/')
        path = safe_file(session.source.directory / 'agent', name)
        if path is None or path.suffix.lower() not in {'.py', '.ts', '.js', '.mjs', '.json', '.toml', '.yaml', '.yml', '.md', '.sql'}:
            continue
        old = next((item for item in files if item['path'] == name), None)
        if old is not None and not old['truncated']:
            continue
        if old is None and len(files) >= session.settings.max_files:
            continue
        used = sum(len(item['content'].encode('utf-8')) for item in files if item is not old)
        remaining = min(session.settings.max_requested_file_bytes,
                        session.settings.max_requested_context_bytes - used)
        if remaining <= 0:
            continue
        with path.open('rb') as stream:
            raw = stream.read(remaining + 1)
        truncated = len(raw) > remaining
        try:
            decoder = codecs.getincrementaldecoder('utf-8-sig')(errors='strict')
            content = decoder.decode(raw[:remaining], final=not truncated)
        except UnicodeError:
            continue
        if '\0' in content:
            continue
        content = redact(content, session.environ)
        encoded = content.encode('utf-8')
        if len(encoded) > remaining:
            content, truncated = encoded[:remaining].decode('utf-8', errors='ignore'), True
        entry = {'path': name, 'build_context_path': 'agent/' + name,
                 'content': content, 'truncated': truncated}
        if old is not None and entry == old:
            continue
        if old is not None:
            files[files.index(old)] = entry
        else:
            files.append(entry)
        requested.append(name)
    if requested:
        session.context['content_bytes'] = sum(len(item['content'].encode('utf-8')) for item in files)
        supplied = {item['path'] for item in files}
        session.context['omitted'] = [item for item in session.context['omitted'] if item['path'] not in supplied]
        record_context(session)
    return requested


def record_context(session):
    context = session.context
    save_json(session.attempt / 'context.json', {
        **{key: value for key, value in context.items() if key != 'files'},
        'files': [{'path': item['path'], 'truncated': item['truncated']} for item in context['files']]})


def generate_with_source(session, payload, *, prompt, schema, stage, checkpoint=None):
    """Ask bounded follow-ups only after valid needs_input cites available local files."""
    for round_number in range(session.settings.source_request_rounds + 1):
        response = session.generate(payload, prompt=prompt, schema=schema)
        if response.get('status') != 'needs_input' or round_number == session.settings.source_request_rounds:
            return response
        if contains_secret(json.dumps(response), session.environ):
            return response
        try:
            validate_response(response, schema, session)
        except ValueError:
            return response
        paths = [match.group() for message in response['missing_information'] for match in PATH.finditer(message)]
        added = add_source_files(session, paths)
        if not added:
            return response
        if checkpoint is not None:
            checkpoint.record_sources(added)
        index = 1 + len(list(stage.glob('source-request-*.json')))
        save_json(stage / f'source-request-{index}.json', {'response': response, 'supplied_files': added})
        session.output_fn('Source evidence: supplied ' + ', '.join(added))
        payload = {**payload, **session.payload(), 'source_request_response': response,
                   'source_request_note': 'Requested existing files are now in context.files. Reassess the actual source; ask only for facts that are still absent.'}
    raise AssertionError('unreachable')
