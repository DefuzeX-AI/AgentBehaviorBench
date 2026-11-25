"""Transport native terminal input as resumable conversation turns."""
import asyncio
import io
import json
from pathlib import Path
import re
import subprocess
import sys


class NativeTerminal:
    def __init__(self, worker=None):
        self.worker = Path(worker) if worker else Path(__file__).with_name('native_worker.py')
        self.process = None

    def invoke(self, value, config=None):
        text = value.get('message', '') if isinstance(value, dict) else str(value)
        if self.process is None:
            self.process = subprocess.Popen(
                [sys.executable, '-X', 'utf8', '-u', str(self.worker)], stdin=subprocess.PIPE,
                stdout=subprocess.PIPE, text=True, encoding='utf-8', bufsize=1)
        if self.process.poll() is not None:
            raise RuntimeError('Native workflow has ended; start a new session')
        # Runtime callback objects belong to the parent process. Network interception
        # remains authoritative for model evidence in this subprocess transport.
        wire_config = {k: v for k, v in (config or {}).items() if k != 'callbacks'}
        self.process.stdin.write(json.dumps({'text': text, 'config': wire_config})+'\n')
        self.process.stdin.flush()
        output = []
        for line in self.process.stdout:
            event = json.loads(line)
            if event['event'] == 'stdout':
                output.append(event['text'])
                sys.stderr.write(event['text'])
                sys.stderr.flush()
            elif event['event'] == 'input_request':
                rendered = re.sub(r'\x1b\[[0-9;]*[A-Za-z]', '', ''.join(output))
                markers = ('Please choose the next step:', 'Clarification Questions',
                           'Do you need additional analysis or modifications?',
                           'Specify areas to modify:', 'Please enter your request:')
                offsets = [rendered.rfind(marker) for marker in markers if marker in rendered]
                if offsets:
                    rendered = rendered[max(offsets):]
                elif len(rendered) > 2000:
                    rendered = rendered[-2000:]
                if not rendered.strip():
                    raise RuntimeError('Native input request had no visible prompt')
                return {'status': 'awaiting_user_input', 'workflow_completed': False,
                        'prompt': rendered.strip()}
            elif event['event'] == 'result':
                self.process.wait(timeout=10)
                return event['value']
            elif event['event'] == 'error':
                raise RuntimeError(event['message'])
        raise RuntimeError(f'Native workflow exited without a result: {self.process.wait()}')

    async def ainvoke(self, value, config=None):
        return await asyncio.to_thread(self.invoke, value, config)

    def close(self):
        if self.process is not None and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5)

    def __del__(self):
        self.close()


def run_native(factory):
    original_in, original_out = sys.stdin, sys.stdout
    def emit(event):
        original_out.write(json.dumps(event, ensure_ascii=False, default=str)+'\n')
        original_out.flush()

    class Output(io.TextIOBase):
        def write(self, text):
            if text:
                emit({'event': 'stdout', 'text': text})
            return len(text)
        def flush(self):
            original_out.flush()

    class Input(io.TextIOBase):
        def readline(self, size=-1):
            emit({'event': 'input_request'})
            line = original_in.readline()
            if not line:
                return ''
            return json.loads(line)['text']+'\n'

    first = json.loads(original_in.readline())
    sys.stdin, sys.stdout = Input(), Output()
    try:
        native = factory()
        result = native.invoke(first['text'], config=first.get('config'))
        emit({'event': 'result', 'value': result})
    except Exception as exc:
        emit({'event': 'error', 'message': f'{type(exc).__name__}: {exc}'})
        raise


def create_graph():
    return NativeTerminal()
