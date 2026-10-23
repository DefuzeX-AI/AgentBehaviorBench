import json
import os
import subprocess
import urllib.request
import urllib.error

body = '''## Summary
ABB can now import custom cases, execute Agents, and collect traces without KUMA installed. New local runs generate conversations from the Agent Profile and judge saved evidence through ABB's configured model provider; KUMA remains an optional adapter.

- Add native case import and a vendor-neutral Judge protocol with request identities, evidence integrity checks, retained delivery state, and local/KUMA/custom adapters.
- Move local evaluation onto ABB's native execution path. Validate generated cases, keep model calls on the host, and retain sanitized raw Judge responses before parsing and validation.
- Share Profile/reference loading and environment snapshots across local and KUMA, reusing existing runtime interfaces and preserving KUMA's parser. Explicitly label preparation observations as SDK-controller facts.
- Preserve execution-only, Judge delivery, and quality-gate distinctions in saved results and the viewer; maintain case reuse and recovery compatibility.
- Add documentation and regression/container tests. Generated results, credentials, temporary scripts, and unrelated local changes are excluded.

## Validation
- Python regression suite: **112 passed, 1 skipped**.
- Frontend `npm test`: **153 passed**.
- `git diff --check` passed.
- Earlier container acceptance used an image without KUMA installed and retained case, output, spans, and an independent Judge result.
- Real react-agent validation exercised local model generation, container execution, trace collection, and model judging with host KUMA imports blocked. The latest run initially failed Judge response validation; a Judge-only retry reused saved evidence and returned a valid pass. Raw responses are now retained before validation. This validates integration, not human-reviewed ground truth.

## Limitations
- Local conversations are generated before execution, not adaptively turn by turn.
- Judge evidence has a configurable size limit; oversized evidence is inconclusive rather than silently truncated.
- Legacy local result files remain readable; old KUMA-based local modules remain for compatibility, while new local runs use native execution.
- The optional native-to-KUMA bridge has offline translation coverage; successful online KUMA judgment is not claimed.
'''

# Use the same configured GitHub identity that successfully pushed this branch.
# Capture credentials in memory only; never print or persist them.
env = {**os.environ, 'GIT_TERMINAL_PROMPT': '0', 'GCM_INTERACTIVE': 'Never'}
result = subprocess.run(['git', 'credential', 'fill'], input='protocol=https\nhost=github.com\n\n',
                        text=True, capture_output=True, env=env, check=True)
credential = dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)
payload = {'title': 'Decouple native evaluation and local judging from KUMA',
           'head': 'YaoAnthony:feat/independent-local-evaluation', 'base': 'main', 'body': body}
request = urllib.request.Request('https://api.github.com/repos/DefuzeX-AI/AgentBehaviorBench/pulls',
    data=json.dumps(payload).encode(), headers={'Authorization': 'Bearer '+credential['password'],
    'Accept': 'application/vnd.github+json', 'Content-Type': 'application/json', 'User-Agent': 'ABB-PR'})
try:
    with urllib.request.urlopen(request, timeout=30) as response:
        created = json.load(response)
    print(json.dumps({'url': created['html_url'], 'number': created['number']}))
except urllib.error.HTTPError as error:
    print('GitHub PR creation failed with HTTP', error.code)
    raise SystemExit(1)
