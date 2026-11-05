"""Adapt SDK text to GigaAgent's native CLI graph lifecycle.

The upstream entrypoint giga_agent.agents.run constructs GigaAgent and exposes
agent.graph. This module constructs a fresh instance of the same GigaAgent class
instead of importing that module's shared instance. It does not launch the CLI,
HTTP server or frontend, or replace native reasoning, middleware or tools.

Input example: 'Calculate the compound annual growth rate from 100 to 150 over five years.'
Text, or exactly {'message': text}, becomes one native HumanMessage. JSON-looking
text remains text; runtime configuration is separate from the business input.
The result is terminal assistant text, not a fabricated answer or partial state.
No upload, previous messages or attachment metadata is synthesized.

The selected deployment uses CLI mode, the native local_jupyter sandbox with
GIGA_AGENT_CLI_NO_SANDBOX=true (secure execution OFF; no bubblewrap), local
SQLite checkpointing, disabled scraping and disabled background sweepers and
scheduler. That CLI flag also disables the CLI write-directory safety policy;
confinement is the Case container. LangGraph replacement mode injects
OPENAI_API_KEY; the binding points the native OpenAI connector at
https://api.openai.com/v1 to match agent.toml openai-chat admission. The
interceptor replaces the upstream target and model. Credentials are never
embedded in this module or returned.

RunnableConfig is shallow-copied, retaining live callbacks and unrelated fields.
Its existing thread identifier is preserved. The native CLI identity and an owned
checkpointer are defaults. Ordinary auto-approval is the explicitly selected
oneshot policy; pending destructive, frontend or MCP review is never resumed
implicitly. Such a suspended execution raises and cannot accept another message.

One binding owns a temporary workspace, checkpoint connection and native runtime
resources until close/aclose. These files are private, not persistent benchmark
artifacts. GigaAgent uses process-global settings and service managers, so native
runtime ownership is exclusive within a worker. Use an isolated oneshot worker,
not an already-running GigaAgent application. Dependencies and network admission
remain installation/deployment responsibilities.

Async invocation and aclose must run on the same event loop. Sync invocation
reuses an asyncio.Runner so loop-bound resources survive repeated calls safely.
Do not mix synchronous and asynchronous invocation on one instance.
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Mapping
from contextlib import AsyncExitStack
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Lock
from uuid import uuid4


_RUNTIME_OWNER = Lock()
_ENV_NAMES = (
    'GIGA_AGENT_RUNTIME',
    'GIGA_AGENT_RUNTIME_LOCAL',
    'GIGA_AGENT_PROJECT_ROOT',
    'GIGA_AGENT_CLI_CWD',
    'GIGA_AGENT_CLI_CONFIG',
    'GIGA_AGENT_CLI_NO_SANDBOX',
    'GIGA_AGENT_SECRET_KEY',
    'GIGA_AGENT_SCRAPER_DISABLED',
    'GIGA_AGENT_SANDBOX_IDLE_SWEEPER_ENABLED',
    'GIGA_AGENT_SANDBOX_ORPHAN_SWEEPER_ENABLED',
    'GIGA_AGENT_SCHEDULER_ENABLED',
    'OPENAI_API_KEY',
    'OPENAI_BASE_URL',
)


class HumanReviewRequired(RuntimeError):
    """The native graph is suspended; no final successful result is available."""


def _message_from_input(value):
    """Accept nonempty text or exactly {message: text}; reject extra fields."""
    if isinstance(value, Mapping):
        if set(value) != {'message'}:
            raise ValueError('Supply text or exactly one message field')
        value = value['message']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('The current message must be nonempty text')
    return value


# Matches [[llm_interception.routes]] openai-chat in agent.toml. Replacement
# mode rewrites the upstream host and model; do not point at ABB_AGENT_MODEL_*.
_OPENAI_ADMITTED_BASE = 'https://api.openai.com/v1'


def _replacement_openai():
    """Use the worker-injected OpenAI credential and the admitted openai-chat base."""
    credential = os.environ.get('OPENAI_API_KEY', '').strip()
    if not credential:
        raise RuntimeError('OPENAI_API_KEY must be supplied by the interception worker')
    # Placeholder source model; the interceptor substitutes the run target model.
    model = (os.environ.get('OPENAI_MODEL') or 'gpt-4.1-mini').strip()
    if not model:
        raise RuntimeError('OPENAI_MODEL must not be empty when set')
    return model, _OPENAI_ADMITTED_BASE, credential


class GigaAgentBinding:
    """Own one native CLI runtime and its checkpoint/resource lifecycle."""

    def __init__(self):
        self._runner = None
        self._loop = None
        self._gate = None
        self._closed = False
        self._suspended = False
        self._leased = False
        self._environment = None
        self._directory = None
        self._workspace = None
        self._stack = None
        self._native = None
        self._checkpointer = None
        self._native_started = False
        self._thread_id = str(uuid4())

    def _bind_loop(self):
        loop = asyncio.get_running_loop()
        if self._loop is None:
            self._loop = loop
            self._gate = asyncio.Lock()
        elif self._loop is not loop:
            raise RuntimeError('Use this binding and its cleanup on their original event loop')

    async def _initialize(self):
        if self._native is not None:
            return
        model, base, credential = _replacement_openai()
        if not _RUNTIME_OWNER.acquire(blocking=False):
            raise RuntimeError('Another binding owns the process-global GigaAgent runtime')
        self._leased = True
        try:
            self._environment = {name: os.environ.get(name) for name in _ENV_NAMES}
            self._directory = TemporaryDirectory(prefix='abb-giga-agent-')
            root = Path(self._directory.name)
            project = root / 'home'
            self._workspace = root / 'workspace'
            project.mkdir()
            self._workspace.mkdir()
            runtime_conf = {
                'llm': {
                    '__type': 'openai',
                    'connector': {'__type': 'openai', 'base_url': base},
                    'model_id': model,
                },
                'sandbox': 'local_jupyter',
            }
            os.environ.update({
                'GIGA_AGENT_RUNTIME': 'cli',
                'GIGA_AGENT_RUNTIME_LOCAL': 'true',
                'GIGA_AGENT_PROJECT_ROOT': str(project),
                'GIGA_AGENT_CLI_CWD': str(self._workspace),
                'GIGA_AGENT_CLI_CONFIG': json.dumps(runtime_conf),
                # Matches cli_chat when disabling protected local_jupyter launch.
                # Without this, CliRuntimeResolver forces safe_execution=true and
                # requires bubblewrap; confinement stays the Case container.
                'GIGA_AGENT_CLI_NO_SANDBOX': 'true',
                'GIGA_AGENT_SCRAPER_DISABLED': 'true',
                'GIGA_AGENT_SANDBOX_IDLE_SWEEPER_ENABLED': 'false',
                'GIGA_AGENT_SANDBOX_ORPHAN_SWEEPER_ENABLED': 'false',
                'GIGA_AGENT_SCHEDULER_ENABLED': 'false',
                'OPENAI_API_KEY': credential,
                'OPENAI_BASE_URL': base,
            })
            # Match cli_chat: project dir + secret before the final settings cache.
            from giga_agent.core.paths import ensure_giga_agent_dir
            ensure_giga_agent_dir()
            from giga_agent.cli.utils.secret_key import ensure_dev_secret_key_env
            ensure_dev_secret_key_env()
            from giga_agent.conf import reset_settings_cache
            reset_settings_cache()
            from giga_agent.core.agent.cli_conf import load_cli_conf, reset_cli_conf_cache
            reset_cli_conf_cache()
            load_cli_conf()
            from giga_agent.core.cache import setup_cache
            setup_cache()

            # Registries and the complete default module set remain upstream.
            self._native_started = True
            from giga_agent.agents.giga_agent import GigaAgent
            self._native = GigaAgent()
            # This public method is the BaseAgent lifespan's migration path.
            # The HTTP lifespan itself is not entered: it starts other services.
            await self._native.run_startup_migrations()

            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
            checkpoint_dir = project / 'langgraph'
            checkpoint_dir.mkdir()
            self._stack = AsyncExitStack()
            self._checkpointer = await self._stack.enter_async_context(
                AsyncSqliteSaver.from_conn_string(str(checkpoint_dir / 'checkpoints.db'))
            )
        except BaseException:
            self._closed = True
            try:
                await self._cleanup()
            except BaseException:
                # Preserve the original initialization failure, not a success
                # result or a potentially credential-bearing cleanup message.
                pass
            raise

    async def ainvoke(self, value, config=None):
        """Execute one current message and return completed native assistant text.

        Args:
            value: Nonempty string or exactly {'message': nonempty_string}.
            config: RunnableConfig or None. Callbacks, tags, metadata, explicit
                limits and thread identifiers survive the shallow merge.
        Returns:
            A string projected from the last native AIMessage's text content.
        Raises:
            ValueError for invalid boundary/configuration shapes;
            HumanReviewRequired for suspended native work;
            RuntimeError for closed bindings, loop misuse or absent final text.
            Native initialization and execution failures propagate unchanged.
        Ownership:
            Resources persist until aclose on this same loop. No transcript is
            assembled; the native SQLite checkpointer owns session state.
        """
        message = _message_from_input(value)
        if self._closed:
            raise RuntimeError('GigaAgent binding is closed')
        if config is not None and not isinstance(config, Mapping):
            raise ValueError('config must be a RunnableConfig mapping or None')
        self._bind_loop()
        async with self._gate:
            if self._closed:
                raise RuntimeError('GigaAgent binding is closed')
            if self._suspended:
                raise HumanReviewRequired('The previous native run still requires explicit human review')
            run_config = dict(config) if config is not None else {}
            original = run_config.get('configurable')
            if original is not None and not isinstance(original, Mapping):
                raise ValueError('configurable must be a mapping')
            configurable = dict(original) if original is not None else {}
            disabled = configurable.get('disabled_modules')
            if disabled is None:
                disabled = []
            if not isinstance(disabled, (list, tuple, set)) or any(
                not isinstance(item, str) for item in disabled
            ):
                raise ValueError('disabled_modules must be a collection of module names')
            configurable['disabled_modules'] = list(dict.fromkeys([*disabled, 'scraper']))
            configurable.setdefault('thread_id', self._thread_id)
            if not configurable['thread_id']:
                raise ValueError('thread_id must not be empty')
            # Explicit deployment policy, not an inferred benchmark shortcut.
            configurable['auto_approve'] = True
            run_config['configurable'] = configurable
            await self._initialize()

            from giga_agent.core.agent.runtime_resolver import RuntimeResolver
            resolver = await RuntimeResolver.create(run_config)
            if 'langgraph_auth_user' not in configurable:
                configurable['langgraph_auth_user'] = {'identity': str(resolver.user.id)}
            from langgraph.constants import CONFIG_KEY_CHECKPOINTER
            configurable.setdefault(CONFIG_KEY_CHECKPOINTER, self._checkpointer)
            from langchain_core.messages import AIMessage, HumanMessage
            # Preserve the entire request, including JSON-looking strings and
            # literal @file references; do not infer files or rewrite the task.
            result = await self._native.graph.ainvoke(
                {'messages': [HumanMessage(content=message)]}, config=run_config
            )
            snapshot = await self._native.graph.aget_state(run_config)
            interrupted = isinstance(result, Mapping) and bool(result.get('__interrupt__'))
            if snapshot.next or interrupted:
                self._suspended = True
                raise HumanReviewRequired(
                    'Native execution is suspended for review or external interaction; '
                    'the binding does not approve destructive actions or fabricate frontend responses'
                )
            if not isinstance(result, Mapping):
                raise RuntimeError('The native graph did not return message state')
            final = next(
                (item for item in reversed(result.get('messages', [])) if isinstance(item, AIMessage)),
                None,
            )
            if final is None or final.tool_calls:
                raise RuntimeError('Native execution has no terminal assistant message')
            content = final.content
            if isinstance(content, str):
                text = content
            elif isinstance(content, list):
                text = '\n\n'.join(
                    part if isinstance(part, str) else part.get('text', '')
                    for part in content
                    if isinstance(part, str) or (
                        isinstance(part, Mapping)
                        and part.get('type') == 'text'
                        and isinstance(part.get('text'), str)
                    )
                )
            else:
                raise RuntimeError('Native assistant content has no supported text representation')
            if not text.strip():
                raise RuntimeError('Native execution completed without final assistant text')
            return text

    def invoke(self, value, config=None):
        """Synchronously execute the same input/config contract using a retained loop.

        Returns terminal assistant text and propagates ainvoke failures. Requires
        no active event loop in this thread; async callers must await ainvoke.
        Call close when finished so the Runner and native resources are released.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError('An event loop is active; await ainvoke instead')
        if self._closed:
            raise RuntimeError('GigaAgent binding is closed')
        if self._runner is None:
            if self._loop is not None:
                raise RuntimeError('Do not mix async and synchronous use of this binding')
            self._runner = asyncio.Runner()
        return self._runner.run(self.ainvoke(value, config=config))

    async def _cleanup(self):
        """Attempt every owned cleanup step, including after partial initialization."""
        errors = []
        if self._stack is not None:
            stack, self._stack = self._stack, None
            try:
                await stack.aclose()
            except BaseException as exc:
                errors.append(exc)
        self._checkpointer = None
        if self._native_started:
            # These are the native BaseAgent lifespan/CLI shutdown entrypoints.
            # Continue cleanup if one fails, without printing exception details.
            try:
                from giga_agent.sandbox.local_jupyter.manager import get_local_jupyter_server_manager
                await get_local_jupyter_server_manager().stop()
            except BaseException as exc:
                errors.append(exc)
            try:
                from giga_agent.vectorstores.qdrant import shutdown_qdrant_client
                await shutdown_qdrant_client()
            except BaseException as exc:
                errors.append(exc)
            try:
                from giga_agent.modules.mcp.pool import shutdown_pool
                await shutdown_pool()
            except BaseException as exc:
                errors.append(exc)
            try:
                from giga_agent.core.process_supervisor import get_process_supervisor
                await asyncio.to_thread(get_process_supervisor().stop_all)
            except BaseException as exc:
                errors.append(exc)
            try:
                from giga_agent.core.db import dispose_engine
                await dispose_engine()
            except BaseException as exc:
                errors.append(exc)
        self._native_started = False
        self._native = None
        if self._directory is not None:
            directory, self._directory = self._directory, None
            try:
                directory.cleanup()
            except BaseException as exc:
                errors.append(exc)
        self._workspace = None
        if self._environment is not None:
            environment, self._environment = self._environment, None
            for name, previous in environment.items():
                if previous is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = previous
            try:
                from giga_agent.conf import reset_settings_cache
                from giga_agent.core.agent.cli_conf import reset_cli_conf_cache
                reset_settings_cache()
                reset_cli_conf_cache()
                from giga_agent.core.paths import ensure_giga_agent_dir
                ensure_giga_agent_dir.cache_clear()
            except BaseException as exc:
                errors.append(exc)
        if self._leased:
            self._leased = False
            _RUNTIME_OWNER.release()
        if errors:
            raise RuntimeError('One or more native GigaAgent cleanup operations failed') from None

    async def aclose(self):
        """Release owned resources on the invocation loop; safe to repeat.

        Raises RuntimeError for cross-loop cleanup or native cleanup failure.
        It does not close a caller-owned event loop or external checkpointer.
        """
        if self._loop is None:
            self._closed = True
            return
        self._bind_loop()
        async with self._gate:
            self._closed = True
            await self._cleanup()

    def close(self):
        """Close resources created by invoke and its retained synchronous Runner.

        Async users must await aclose on their invocation loop. This method
        rejects active-loop use rather than discarding awaitable resources.
        """
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError('An event loop is active; await aclose instead')
        if self._runner is not None:
            runner, self._runner = self._runner, None
            try:
                runner.run(self.aclose())
            finally:
                runner.close()
        elif self._loop is None:
            self._closed = True
        elif self._closed and not self._leased:
            return
        else:
            raise RuntimeError('Async resources must be released with aclose on their original loop')


def create_graph():
    """Return a fresh synchronous/async SDK-compatible GigaAgent binding.

    Takes no arguments. Native setup is deferred until invocation, so the
    factory returns an invokable object rather than a coroutine or generator.
    Example: invoke('Explain what tools are available', config=run_config).
    The caller owns close/aclose; no execution or certification occurs here.
    """
    return GigaAgentBinding()
