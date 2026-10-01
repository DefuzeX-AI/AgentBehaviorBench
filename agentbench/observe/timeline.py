"""Read persisted timings without starting, resuming, or modifying a run."""
from datetime import datetime
import json
import math
import time


def timeline(api):
    operations, warnings = {}, []
    names = ['timing.jsonl', 'evaluation/timing.jsonl']
    names.extend(sorted(path.name for path in api.directory.glob('timing-recovery-*.jsonl')))
    for name in names:
        try:
            path = api.file(name)
            with path.open(encoding='utf-8') as stream:
                for line in stream:
                    if not line.strip():
                        continue
                    try:
                        row = json.loads(line)
                        data = row['data']
                        if row.get('event') != 'operation' or not isinstance(data.get('id'), str):
                            continue
                        if not all(isinstance(data.get(k), (int, float)) and math.isfinite(data[k])
                                   for k in ('start_ms', 'end_ms', 'duration_ms')):
                            raise ValueError('Invalid timing')
                        if data['duration_ms'] < 0 or data['end_ms'] < data['start_ms']:
                            raise ValueError('Invalid interval')
                        observed = datetime.fromisoformat(row['timestamp'].replace('Z', '+00:00')).timestamp() * 1000
                        operations[data['id']] = {**data, 'observed_at_ms': observed}
                    except (ValueError, KeyError, TypeError, AttributeError):
                        warnings.append(f'{name}: incomplete or invalid timing record')
        except FileNotFoundError:
            pass
        except (OSError, ValueError):
            warnings.append(f'{name}: unavailable')
    otel = api.spans()
    return {'schema': 'abb.timeline.v1', 'operations': list(operations.values()),
            'spans': otel['spans'], 'metadata': api.read('run.json') or {},
            'observed_at_ms': time.time_ns() / 1e6,
            'warnings': list(dict.fromkeys(warnings + otel['warnings']))}


if __name__ == '__main__':
    import sys
    from pathlib import Path
    from .view_api import RunViewAPI
    print(json.dumps(timeline(RunViewAPI(Path(sys.argv[1])))))
