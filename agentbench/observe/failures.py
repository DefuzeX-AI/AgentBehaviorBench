"""Evidence-backed tool failures for display, never for verdicts or retry policy."""
import json
from pathlib import Path

RULES = json.loads(Path(__file__).with_name('failure_rules.json').read_text(encoding='utf-8'))


def tool_failures(api, folder):
    """Read bounded, already-redacted framework events for one invocation."""
    spans, failures, seen = {}, [], set()
    relative = f'{folder}/framework.jsonl'
    try:
        with api.file(relative).open(encoding='utf-8') as stream:
            consumed = 0
            for number in range(100000):
                line = stream.readline(262145)
                consumed += len(line)
                if not line or consumed > 8 * 1024 * 1024:
                    break
                if len(line) > 262144:
                    break
                try:
                    row = json.loads(line)
                except ValueError:
                    continue
                if not isinstance(row, dict) or not isinstance(row.get('data'), dict):
                    continue
                data = row['data']
                sid = data.get('span_id')
                if not isinstance(sid, str):
                    continue
                if row.get('event') == 'span_start' and data.get('kind') == 'tool':
                    spans[sid] = str(data.get('name') or 'Tool')[:200]
                if row.get('event') != 'span_error' or sid not in spans:
                    continue
                error = data.get('error')
                code = error.get('code') if isinstance(error, dict) else None
                message = error.get('message') if isinstance(error, dict) else error
                if not isinstance(message, str) or not message.strip():
                    continue
                tool = spans[sid]
                provider = tool.split('.')[0]
                rule = next((r for r in RULES if r['provider'] == provider and
                             (code in r['codes'] if code else message.startswith(r['message_prefix']))), None)
                key = (tool, message)
                if key in seen:
                    continue
                seen.add(key)
                failures.append({'category': rule['category'] if rule else 'tool_error',
                                 'summary': rule['summary'] if rule else f'{tool} failed',
                                 'message': message[:2000], 'tool': tool,
                                 'source': f'{relative}:{number + 1}', 'span_id': sid})
                if len(failures) == 10:
                    break
    except (OSError, ValueError):
        pass
    return failures
