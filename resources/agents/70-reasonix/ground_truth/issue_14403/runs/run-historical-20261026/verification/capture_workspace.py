"""Read-only observer preserving fixture versions before SDK workspace cleanup."""
import hashlib, json, sys, time
from pathlib import Path
root=Path('\\\\?\\'+str(Path(__file__).resolve().parent))
run=sys.argv[1]
out=root/'snapshots'/run
out.mkdir(parents=True,exist_ok=True)
seen=set()
deadline=time.monotonic()+600
while time.monotonic()<deadline:
    for p in (root/run).glob('agents/*/cases/*/trajectory/.abb-workspace-*/settings.ini'):
        try:
            raw=p.read_bytes()
        except FileNotFoundError:
            continue
        sha=hashlib.sha256(raw).hexdigest()
        if sha not in seen:
            seen.add(sha)
            (out/(sha+'.ini')).write_bytes(raw)
            record={'observed_at_unix':time.time(),'source':str(p),'sha256':sha,'hex':raw.hex(),'bare_lf':len(raw.replace(b'\r\n',b'').split(b'\n'))-1}
            with (out/'observations.jsonl').open('a',encoding='utf-8') as f:
                f.write(json.dumps(record)+'\n')
            print(json.dumps(record),flush=True)
            if b'timeout=30' in raw:
                sys.exit(0)
    time.sleep(0.25)
raise SystemExit('No edited fixture observed within 600 seconds')
