"""Sync and async callers share one owned event loop for persistent ACP resources."""
import asyncio
import threading
from pathlib import Path
from agentbench.adapter.base import AdapterInvocation
from .config import ACPConfig


class ACPAdapter:
    network_mode = 'observe'
    build_requirements = Path(__file__).with_name('requirements.txt')

    def __init__(self, config):
        self.config = config
        self._loop = self._thread = self._session = None
        self._closed = False
        self._lock = threading.RLock()

    @classmethod
    def from_agent_dir(cls, root):
        return cls(ACPConfig.from_agent_dir(root))

    @property
    def is_loaded(self):
        return self._session is not None and not self._session.closed

    def load(self):
        """Prepare the owned loop; launch/handshake occurs at the first input."""
        with self._lock:
            if self._closed:
                raise RuntimeError('ACP adapter is closed')
            if self._loop is None:
                from .session import ACPSession
                self._loop = asyncio.new_event_loop()
                self._session = ACPSession(self.config)
                self._thread = threading.Thread(target=self._serve, name='abb-acp', daemon=True)
                self._thread.start()
        return self

    def _serve(self):
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_forever()
        finally:
            pending = asyncio.all_tasks(self._loop)
            for task in pending:
                task.cancel()
            self._loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
            self._loop.run_until_complete(self._loop.shutdown_asyncgens())
            self._loop.close()

    def _submit(self, value, config):
        text = self.config.text_input(value)
        self.load()
        callbacks = (config or {}).get('callbacks', [])
        callbacks = [item for item in callbacks if callable(getattr(item, 'on_acp_event', None))]
        return asyncio.run_coroutine_threadsafe(self._session.invoke(text, callbacks), self._loop)

    def invoke(self, value, *, run_config=None):
        """Return normalized text and protocol summary; retain the session for the next input."""
        result = self._submit(value, run_config).result()
        return AdapterInvocation(*result)

    async def ainvoke(self, value, *, run_config=None):
        """Async counterpart; cancellation waits for owned process cleanup."""
        future = self._submit(value, run_config)
        try:
            return AdapterInvocation(*await asyncio.shield(asyncio.wrap_future(future)))
        except asyncio.CancelledError:
            future.cancel()
            await asyncio.shield(self.aclose())
            raise

    def close(self):
        with self._lock:
            if self._closed:
                return
            self._closed = True
            if self._loop is None:
                return
            try:
                asyncio.run_coroutine_threadsafe(self._session.close(), self._loop).result(
                    timeout=self.config.cleanup_timeout * 4 + 2)
            finally:
                self._loop.call_soon_threadsafe(self._loop.stop)
                self._thread.join(timeout=self.config.cleanup_timeout * 4 + 2)
                if self._thread.is_alive():
                    raise RuntimeError('ACP event loop did not stop within its cleanup budget')

    async def aclose(self):
        await asyncio.to_thread(self.close)
