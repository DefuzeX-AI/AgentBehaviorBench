import json, sys
from pathlib import Path
root = Path('\\\\?\\' + str(Path(__file__).resolve().parent))
arm = sys.argv[1]
directory = root / ('b' if arm == 'before' else 'a')
for p in directory.glob('agents/*/cases/*/trajectory/*/steps/*/result.json'):
    d=json.loads(p.read_text(encoding='utf-8'))
    print('RESULT',json.dumps(d,ensure_ascii=False)[:18000])
    for line in (p.parent/'framework.jsonl').read_text(encoding='utf-8').splitlines():
        e=json.loads(line)
        if e.get('event') in ('span_start','span_end'):
            print('TOOL',json.dumps(e,ensure_ascii=False)[:6000])
for p in directory.rglob('settings.ini'):
    b=p.read_bytes()
    print('BYTES',str(p),repr(b))
