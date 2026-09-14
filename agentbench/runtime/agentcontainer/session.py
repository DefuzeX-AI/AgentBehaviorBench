"""Agent object/resource ownership for a single Case or standalone invocation."""
import os
from types import SimpleNamespace
from agentbench.adapter.factory import DEFAULT_ADAPTER_FACTORY


class AgentSession:
    """Own one Agent instance and its resources for one Case attempt.

    Context and storage contents belong to the Agent. This class only loads,
    reuses and closes its adapter; it never reads or writes conversation memory.
    """
    def __init__(self):
        self.adapter = None
        self.identity = None
        self.closed = False
        self.invocations = 0

    def load(self, root, envelope):
        """Return the same adapter for this Agent/session, loading it once.

        Args:
            root: Agent unit directory.
            envelope: Invocation identity with agent_id, framework, run_id and
                an optional stable session_id (defaults to run_id).
        Returns:
            Loaded adapter whose native resources survive until aclose().
        Raises:
            ValueError: Closed session or a different Agent/Case identity.
        """
        identity = (root.resolve(), envelope['agent_id'], envelope['framework'],
                    envelope.get('session_id', envelope['run_id']))
        if self.closed or (self.identity is not None and self.identity != identity):
            raise ValueError('Agent session cannot be reused across Cases or Agents')
        if self.adapter is None:
            self.identity = identity
            self.adapter = DEFAULT_ADAPTER_FACTORY.create(
                SimpleNamespace(path=root, framework=envelope['framework']))
            self.adapter.load()
        self.invocations += 1
        return self.adapter

    def snapshot(self):
        return {'pid': os.getpid(), 'session_id': self.identity[-1] if self.identity else None,
                'adapter_initializations': int(self.identity is not None),
                'invocations': self.invocations, 'closed': self.closed}

    async def aclose(self):
        if self.closed:
            return
        self.closed = True
        if self.adapter is not None:
            close = getattr(self.adapter, 'aclose', None)
            if callable(close):
                await close()
            else:
                self.adapter.close()
