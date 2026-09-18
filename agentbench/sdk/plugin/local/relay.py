"""Host side of the local Judge: answer a container's request with one model call.

The host already holds the upstream credential the interceptor uses, so by default
the Judge asks the Agent's own OpenAI-compatible model target. ``ABB_LOCAL_JUDGE_*``
select another endpoint. The relay answers at most one request per Run, builds the
prompt itself from bounded fields, and never places the key in the container.
"""
import json
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from urllib.parse import urlsplit

from agentbench.observe.store import redact
from agentbench.runtime.interception import resolve_model_provider
from agentbench.sdk.common.artifacts import Artifacts

from .judge import REQUEST, REQUEST_SCHEMA, RESPONSE, RESPONSE_SCHEMA, bounded, verdict_fields, write_shared

SYSTEM = (
    'You review an integration smoke test of an AI agent. The agent answered a short, generic '
    'conversation; each step has the input it received and the output it returned. Decide only '
    'whether the outputs are coherent, relevant replies to their inputs and to the earlier steps. '
    'Be lenient: do not judge style, length or factual depth, and accept a refusal that explains '
    'itself. Report "issue" only for an empty, garbled, off-topic or self-contradictory output, or '
    'a step that ignores the conversation so far. Reply with only a JSON object: '
    '{"status": "pass" or "issue", "confidence": "low", "medium" or "high", '
    '"reason": "<one sentence>", "issues": [{"input_id": "<step id>", "message": "<problem>"}]}'
)
RETRYABLE = frozenset({408, 409, 425, 429, 500, 502, 503, 504})
LOOPBACK = frozenset({'localhost', '127.0.0.1', '::1'})


@dataclass(frozen=True, slots=True)
class JudgeModel:
    base_url: str
    model: str
    api_key: str = field(repr=False)
    # Three attempts plus backoff must end before the container stops waiting
    # (LocalJudge.timeout), so a slow model is reported as such, not as silence.
    timeout: float = 90.0


def judge_model(environ):
    """Resolve the Judge endpoint: ``ABB_LOCAL_JUDGE_*``, else the Agent's model target."""
    names = ('BASE_URL', 'MODEL', 'API_KEY')
    override = {name: (environ.get(f'ABB_LOCAL_JUDGE_{name}') or '').strip() for name in names}
    credential = 'ABB_LOCAL_JUDGE_API_KEY'
    if all(override.values()):
        base, model, key = (override[name] for name in names)
    else:
        target = resolve_model_provider(environ=environ).resolve(environ)
        credential += f' or {target.credential_env}'
        base = override['BASE_URL'] or target.base_url
        model = override['MODEL'] or target.model
        key = override['API_KEY'] or (environ.get(target.credential_env) or '').strip()
    base = base.rstrip('/')
    parsed = urlsplit(base)
    if (parsed.scheme not in ('https', 'http') or not parsed.hostname
            or (parsed.scheme == 'http' and parsed.hostname not in LOOPBACK)):
        raise ValueError('The local Judge base URL must use HTTPS (plain HTTP only for localhost)')
    if 'anthropic' in parsed.path.lower() or parsed.hostname == 'api.anthropic.com':
        raise ValueError(f'The local Judge calls OpenAI-compatible chat completions, but {base} serves '
                         'Anthropic messages; set ABB_LOCAL_JUDGE_BASE_URL, _MODEL and _API_KEY')
    if not model:
        raise ValueError('The local Judge needs a model: set ABB_LOCAL_JUDGE_MODEL or OPENROUTER_MODEL')
    if not key:
        raise ValueError(f'The local Judge needs an API key: set {credential}')
    return JudgeModel(base, model, key)


def read_request(path):
    """Load the container's request, keeping only bounded step fields."""
    value = json.loads(path.read_text(encoding='utf-8'))
    if not isinstance(value, dict) or value.get('schema') != REQUEST_SCHEMA:
        raise ValueError('Invalid local Judge request')
    steps = value.get('steps')
    if (not isinstance(steps, list) or not 1 <= len(steps) <= 50
            or not all(isinstance(step, dict) for step in steps)):
        raise ValueError('A local Judge request needs 1 to 50 step objects')
    return [{'input_id': bounded(str(step.get('input_id')), 128), 'input': bounded(str(step.get('input'))),
             'output': bounded(str(step.get('output')))} for step in steps]


def json_object(text):
    """Read the reply's JSON object, tolerating code fences or surrounding prose."""
    start, end = text.find('{'), text.rfind('}')
    if start < 0 or end <= start:
        raise ValueError('The Judge model reply contains no JSON object')
    return json.loads(text[start:end + 1])


def ask_model(model, steps):
    """Return the normalized verdict and raw reply for one request."""
    url = model.base_url + '/chat/completions'
    body = json.dumps({'model': model.model, 'temperature': 0, 'max_tokens': 2048, 'messages': [
        {'role': 'system', 'content': SYSTEM},
        {'role': 'user', 'content': json.dumps({'steps': steps}, ensure_ascii=False)}]}).encode()
    headers = {'content-type': 'application/json', 'authorization': f'Bearer {model.api_key}'}
    for attempt in range(3):
        retry = attempt < 2
        try:
            with urllib.request.urlopen(urllib.request.Request(url, body, headers),
                                        timeout=model.timeout) as response:
                data = json.load(response)
            break
        except urllib.error.HTTPError as exc:
            if retry and exc.code in RETRYABLE:
                time.sleep(2 + 3 * attempt)
                continue
            detail = exc.read(300).decode('utf-8', 'replace').replace(model.api_key, '***')
            hint = '; the local Judge needs an OpenAI-compatible /chat/completions endpoint' if exc.code == 404 else ''
            raise RuntimeError(f'HTTP {exc.code} from {url}{hint}: {detail}') from None
        except OSError as exc:
            if retry:
                time.sleep(2 + 3 * attempt)
                continue
            raise RuntimeError(f'Cannot reach {url}: {exc}') from None
    try:
        content = data['choices'][0]['message'].get('content') or ''
    except (KeyError, IndexError, TypeError, AttributeError):
        raise RuntimeError('The Judge model returned no chat completion') from None
    return verdict_fields(json_object(content), {step['input_id'] for step in steps}), content


class JudgeRelay:
    """Answer the first local Judge request of one running container."""

    def __init__(self, directory, model, *, environ=None, ask=ask_model, interval=0.2):
        self.evaluation = directory / 'evaluation'
        self.files = Artifacts(directory, environ=environ)
        self.model = model
        self.ask = ask
        self.interval = interval
        self._stopped = threading.Event()
        self._thread = threading.Thread(target=self._run, name='abb-local-judge', daemon=True)

    def start(self):
        self._thread.start()
        return self

    def stop(self, timeout=5.0):
        self._stopped.set()
        self._thread.join(timeout)

    def _run(self):
        request = self.evaluation / REQUEST
        while not self._stopped.wait(self.interval):
            if request.is_file():
                self._answer(request)
                return

    def _answer(self, path):
        started = time.monotonic()
        record = {'schema': 'abb.local_judge.record.v1', 'base_url': self.model.base_url,
                  'model': self.model.model}
        try:
            verdict, reply = self.ask(self.model, read_request(path))
            answer = {'schema': RESPONSE_SCHEMA, 'model': self.model.model, **verdict}
            record['reply'] = bounded(reply)
        except Exception as exc:
            # The container reports this as the Judge failure; the Run is not retried here.
            answer = {'schema': RESPONSE_SCHEMA, 'error': bounded(f'{type(exc).__name__}: {exc}', 500)}
        answer = redact(answer, self.files.secrets)
        record.update(answer=answer, seconds=round(time.monotonic() - started, 3))
        try:
            write_shared(self.evaluation / RESPONSE, answer)
        finally:
            self.files.save('local-judge.json', record)
