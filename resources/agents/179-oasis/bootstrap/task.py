"""Scan a real local greeting program with the unmodified OASIS CLI."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request

request = json.loads(Path(sys.argv[1]).read_text())
work = Path(request['workspace'])
target = work/'greeting-source'
target.mkdir()
(target/'hello.py').write_text('def greet():\n    return '+repr(request['text'])+'\n\nprint(greet())\n')
os.environ.update(OASIS_LLM_PROVIDER='openai',
    OASIS_VULNERABILITY_DIR='/opt/agent/agent/vulnerability',
    OASIS_OPENAI_BASE_URL=os.environ['ABB_AGENT_MODEL_BASE_URL'],
    OASIS_OPENAI_API_KEY=os.environ['ABB_AGENT_MODEL_API_KEY'])
server = subprocess.Popen(['ollama', 'serve'], stdout=sys.stderr, stderr=sys.stderr)
try:
    for _ in range(60):
        if server.poll() is not None:
            raise RuntimeError('Native Ollama embedding service exited')
        try:
            with urllib.request.urlopen('http://127.0.0.1:11434/api/tags', timeout=1) as response:
                if response.status == 200:
                    break
        except OSError:
            time.sleep(1)
    else:
        raise RuntimeError('Native embedding service did not become ready')
    os.chdir(work)
    code = subprocess.run(['oasis', '--input', str(target), '--provider', 'openai',
        '--models', os.environ['ABB_AGENT_MODEL'], '--scan-model', os.environ['ABB_AGENT_MODEL'],
        '--embed-provider', 'ollama', '--embed-model', 'nomic-embed-text',
        '--output-format', 'json', '--chunk-size', '512', '--threshold', '0'],
        stdout=sys.stderr, stderr=sys.stderr).returncode
    if code:
        raise RuntimeError(f'Native OASIS scanner returned {code}')
    reports = {}
    for path in (work/'security_reports').rglob('*.json'):
        reports[str(path.relative_to(work))] = json.loads(path.read_text())
    if not reports:
        raise RuntimeError('Native OASIS produced no JSON report')
    Path(sys.argv[2]).write_text(json.dumps({'native_reports': reports}, ensure_ascii=False))
finally:
    server.terminate()
    server.wait(timeout=15)
