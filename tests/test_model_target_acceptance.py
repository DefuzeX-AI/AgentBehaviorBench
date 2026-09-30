"""Opt-in real Docker/model acceptance, with reproducible image and trace artifacts.

Set ABB_LIVE_TARGET_ACCEPTANCE=1, ABB_ACCEPTANCE_BASE_IMAGE (cached Python image),
ABB_ACCEPTANCE_CHAT_MODEL and ABB_ACCEPTANCE_EMBEDDING_MODEL. Uses OpenRouter and
the existing OPENROUTER_API_KEY; models are test inputs, not production defaults.
"""
import json
import os
import struct
import subprocess
import zlib
from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _image():
    def chunk(kind, content):
        return struct.pack('>I', len(content)) + kind + content + struct.pack('>I', zlib.crc32(kind + content))
    pixels = bytearray()
    for y in range(128):
        pixels.append(0)
        for x in range(256):
            color = (255, 255, 255)
            if 24 <= y < 104:
                if 24 <= x < 104:
                    color = (255, 0, 0)
                elif 152 <= x < 232:
                    color = (0, 0, 255)
            pixels.extend(color)
    return (b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('>IIBBBBB', 256, 128, 8, 2, 0, 0, 0))
            + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))


AGENT = '''import base64, json, os, ssl, urllib.request
from pathlib import Path
tls = ssl.create_default_context(cafile=os.environ['SSL_CERT_FILE'])
def call(url, body, headers):
    request = urllib.request.Request(url, json.dumps(body).encode(),
        {'Content-Type': 'application/json', **headers})
    with urllib.request.urlopen(request, context=tls, timeout=90) as response:
        return json.load(response)
headers = {'Authorization': 'Bearer ' + os.environ['OPENAI_API_KEY']}
root = 'https://api.openai.com/v1'
image = base64.b64encode(Path('/opt/acceptance/fixture.png').read_bytes()).decode()
prompt = 'Name the colors of the two squares from left to right. Return only the two color names.'
results = {}
results['chat'] = call(root + '/chat/completions', {'model': 'source-chat', 'max_tokens': 16,
    'messages': [{'role': 'user', 'content': 'Reply with the single word READY.'}]}, headers)['choices'][0]['message']['content']
results['vision'] = call(root + '/chat/completions', {'model': 'source-vision', 'max_tokens': 32,
    'messages': [{'role': 'user', 'content': [{'type': 'text', 'text': prompt},
        {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + image}}]}]}, headers)['choices'][0]['message']['content']
vectors = call(root + '/embeddings', {'model': 'source-embedding', 'input': ['hello', 'world']}, headers)
results['embedding_dimensions'] = [len(row['embedding']) for row in vectors['data']]
gemini = call('https://generativelanguage.googleapis.com/v1beta/models/source:generateContent',
    {'contents': [{'role': 'user', 'parts': [{'text': prompt},
        {'inlineData': {'mimeType': 'image/png', 'data': image}}]}],
     'generationConfig': {'maxOutputTokens': 32}}, {'x-goog-api-key': os.environ['GOOGLE_API_KEY']})
results['gemini_vision'] = gemini['candidates'][0]['content']['parts'][0]['text']
print(json.dumps(results), flush=True)
assert results['chat'].strip().strip('.').upper() == 'READY'
for name in ('vision', 'gemini_vision'):
    answer = results[name].lower()
    assert 'red' in answer and 'blue' in answer and answer.index('red') < answer.index('blue'), answer
assert len(results['embedding_dimensions']) == 2 and all(n > 0 for n in results['embedding_dimensions'])
'''


@pytest.mark.skipif(os.environ.get('ABB_LIVE_TARGET_ACCEPTANCE') != '1', reason='Opt-in paid model/Docker acceptance')
def test_chat_images_and_embeddings_through_real_runtime():
    from dotenv import dotenv_values
    from agentbench.observe.store import TraceStore
    from agentbench.runtime.docker.runtime import DockerRuntime

    root = Path(__file__).resolve().parents[1]
    env = {**dotenv_values(root / '.env'), **os.environ}
    assert env.get('OPENROUTER_API_KEY'), 'OPENROUTER_API_KEY is required'
    base = env['ABB_ACCEPTANCE_BASE_IMAGE']
    model, embedding = env['ABB_ACCEPTANCE_CHAT_MODEL'], env['ABB_ACCEPTANCE_EMBEDDING_MODEL']
    run_id = 'model-targets-' + uuid4().hex[:12]
    output = root / 'results/verification' / run_id
    output.mkdir(parents=True)
    service = root / 'agentbench/services/model-interceptor'
    dockerfile = output / 'interceptor.Dockerfile'
    dockerfile.write_text(f'FROM {base}\nCOPY src /opt/updated/src\nENV PYTHONPATH=/opt/updated/src\n')
    image = 'defuzex-agentbench/model-target-acceptance:' + run_id
    build = subprocess.run(['docker', 'build', '-q', '-t', image, '-f', str(dockerfile), str(service)],
                           capture_output=True, text=True, timeout=180)
    (output / 'build.log').write_text(build.stdout + build.stderr, encoding='utf-8')
    assert build.returncode == 0, f'See {output / "build.log"}'
    unit = output / 'agent'
    unit.mkdir()
    (unit / 'fixture.png').write_bytes(_image())
    (unit / 'main.py').write_text(AGENT)
    (unit / 'Dockerfile').write_text(f'FROM {base}\nWORKDIR /opt/acceptance\nCOPY main.py fixture.png ./\nENTRYPOINT []\nUSER 1000:1000\n')
    (unit / 'agent.toml').write_text('''schema_version = "defuzex-bench.agent.v2"
agent_id = "model-target-acceptance"
framework = "langgraph"
[runtime]
type = "docker"
timeout_sec = 360
[build]
context = "."
dockerfile = "Dockerfile"
[launch]
argv = ["python", "/opt/acceptance/main.py"]
[llm_interception]
trust_plugin = "pem-env"
[[llm_interception.credentials]]
id = "openai"
agent_env = "OPENAI_API_KEY"
auth_plugin = "bearer-token"
[[llm_interception.credentials]]
id = "google"
agent_env = "GOOGLE_API_KEY"
auth_plugin = "google-api-key"
''')
    routing = output / 'models.toml'
    routing.write_text(f'''[targets.chat]
provider = "openrouter"
model = {json.dumps(model)}
[targets.vision]
provider = "openrouter"
model = {json.dumps(model)}
input_modalities = ["text", "image"]
[targets.vectors]
provider = "openrouter"
model = {json.dumps(embedding)}
[[rules]]
id = "text"
target = "chat"
protocols = ["openai-chat"]
input = "text"
[[rules]]
id = "images"
target = "vision"
protocols = ["openai-chat", "gemini-content"]
input = "image"
[[rules]]
id = "vectors"
target = "vectors"
protocols = ["openai-embeddings"]
input = "text"
''')
    env.update(ABB_MODEL_ROUTING_CONFIG=str(routing), DEFUZEX_INTERCEPTOR_IMAGE=image, ABB_EGRESS='deny')
    runtime = DockerRuntime(environ=env, artifact_root=output, run_id=run_id,
                            trace_sink=TraceStore(output / 'network.jsonl', run_id, source='interceptor'))
    with runtime.start(SimpleNamespace(path=unit)) as session:
        code = session.wait()
        (output / 'agent.stdout').write_text(session.stdout, encoding='utf-8')
        (output / 'agent.stderr').write_text(session.stderr, encoding='utf-8')
    summary = dict(exit_code=code, chat_model=model, embedding_model=embedding, output=str(output))
    (output / 'summary.json').write_text(json.dumps(summary, indent=2))
    assert code == 0, f'See acceptance artifacts: {output}'
    events = [json.loads(line) for line in (output / 'network.jsonl').read_text().splitlines()]
    requests = [event.get('data', event) for event in events if event.get('event') == 'llm_request']
    # TraceStore keeps the event name at the top level and routing fields in data.
    assert len(requests) == 4, f'Expected four captured model calls: {output}'
    assert {row['target_id'] for row in requests} == {'chat', 'vision', 'vectors'}
    print(f'Acceptance artifacts: {output}')
