# Example 04: initialize an application and close its owned resources

This is the complete existing Waku binding. It illustrates lifecycle management
for an already integrated application; it does not make the initial LangGraph-only
onboarding planner support arbitrary frameworks automatically.

Prerequisites: the image installs Waku and its dependencies, the saved manifest
uses the existing source `abb-langgraph.json`, graph ID `agent`,
`binding="waku_binding.py:create_graph"`, `input_key="message"`, and no output_key.
Model interception supplies OPENAI_API_KEY inside the container. Never include a
real key in the generated file or copy the host's .env into the image.

Input example: `{"message": "What can you help me with?"}`.
Output: all fields of the native LoopResult as a dictionary: reply, tool_calls,
iterations. `respond()` runs the actual native application, not a substitute graph.
Each wrapper owns a private home, SQLite connection and native application.
The lock serializes access, including shutdown. Initialization failure releases
resources already created; nested finally blocks allow later cleanup even if an
earlier close fails. Repeated close is safe.

This implementation accepts BBA config but does not forward LangChain callbacks:
Waku's public respond method does not accept them. Do not claim full tool/graph
trace coverage from the invoke signature alone. Native/interception observation
must be assessed separately during certification and execution.

IMPORTANT: OpenAI selection, SQLite stores and disabled desktop/calendar features
are choices of this existing deployment, not universal defaults to copy. The
binding leaves native state to Waku; do not add synthetic history or memory.

Source snapshot: `resources/agents/05-waku-agent/bindings/waku_binding.py`.

```python
"""Translate one ABB Input into Waku's complete public respond() lifecycle."""
import os
from dataclasses import asdict
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock


def message_from_input(value):
    """Accept current text or exactly {message: text}; never synthesize history."""
    if isinstance(value, dict):
        if set(value) != {'message'}:
            raise ValueError('Waku accepts exactly one current message field')
        value = value['message']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Waku message must be non-empty text')
    return value


class WakuSession:
    def __init__(self):
        self._native = self._connection = self._directory = None
        self._closed = False
        self._lock = RLock()

    def _load(self, context):
        """Configure native storage/provider only; Waku owns all Agent state."""
        if self._native is not None:
            return self._native
        from waku.app import Waku
        from waku.config import Settings
        from waku.db import connect

        options = dict(context or {})
        if set(options) - {'model', 'small_model'}:
            raise ValueError('Unsupported Waku deployment context')
        if not os.environ.get('OPENAI_API_KEY'):
            raise ValueError('OPENAI_API_KEY must be supplied by model interception')
        self._directory = TemporaryDirectory(prefix='abb-waku-')
        home = Path(self._directory.name)
        try:
            settings = Settings(home=home, provider='openai', base_url='https://api.openai.com/v1',
                api_key=os.environ['OPENAI_API_KEY'], model=options.get('model', ''),
                small_model=options.get('small_model', ''), semantic_store='sqlite',
                episodic_store='sqlite', apple_calendar=False, google_calendar=False,
                apple_tools=False, gh_tool=False, experimental=False, otel_endpoint='')
            settings.ensure_home()
            # Native dashboard-supported connection mode; turns are serialized.
            self._connection = connect(home, check_same_thread=False)
            self._native = Waku(settings=settings, conn=self._connection)
        except BaseException:
            self.close()
            raise
        return self._native

    def invoke(self, value, config=None, *, context=None):
        """Return every field of the native LoopResult, without replacing reply.

        Args: value is the current Input; config is the ABB callback context;
            context selects native main/small model IDs. No chat history is added.
        Returns: {reply, tool_calls, iterations}, the complete native LoopResult.
        Raises: native execution errors and invalid input pass through unchanged.
        """
        message = message_from_input(value)
        with self._lock:
            if self._closed:
                raise RuntimeError('Waku session is closed')
            return asdict(self._load(context).respond(message, source='cli', stream=False))

    def close(self):
        """Close the native application, owned SQLite connection and private home."""
        with self._lock:
            self._closed = True
            native, self._native = self._native, None
            connection, self._connection = self._connection, None
            directory, self._directory = self._directory, None
            try:
                if native is not None:
                    native.close()
            finally:
                try:
                    if connection is not None:
                        connection.close()
                finally:
                    if directory is not None:
                        directory.cleanup()


def create_graph():
    return WakuSession()
```
