"""Historical builds only: run `reasonix acp`, rewriting the non-ACP stopReason "error".

v1.23-v1.25 answer session/prompt with stopReason "error" when a turn is paused by
their final-answer gate. ACP only defines end_turn, max_tokens, max_turn_requests,
refusal and cancelled, so the client rejects the whole response. The value is mapped
to "end_turn" (the turn did end) and every rewrite is logged to stderr; all other
bytes pass through unchanged.
"""
import json
import signal
import subprocess
import sys

child = subprocess.Popen(sys.argv[1:], stdout=subprocess.PIPE)
for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
    signal.signal(sig, lambda number, _frame: child.send_signal(number))
out = sys.stdout.buffer
for line in child.stdout:
    if b'"stopReason"' in line and b'"error"' in line:
        try:
            message = json.loads(line)
            result = message.get('result')
            if isinstance(result, dict) and result.get('stopReason') == 'error':
                result['stopReason'] = 'end_turn'
                line = (json.dumps(message, ensure_ascii=False, separators=(',', ':')) + '\n').encode()
                print('reasonix historical shim: mapped stopReason "error" to "end_turn"', file=sys.stderr, flush=True)
        except ValueError:
            pass
    out.write(line)
    out.flush()
sys.exit(child.wait())
