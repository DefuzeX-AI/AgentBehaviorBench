"""Deliver one current BBA Case input to OmniWriter's production orchestrator.

Native entrypoint, confirmed from the imported source: the upstream CLI
(``main.py``) constructs ``WriterAgentOrchestrator`` from
``src/pipeline/orchestrator.py`` and calls the public run lifecycle
(``run_sync``/``run``), which validates the topic, builds the initial
MessageState (``user_query`` plus one user-role message carrying the topic),
invokes the compiled LangGraph pipeline (head routing, title decomposition,
Tavily search, retrieval simplification, outline generation and review,
parallel chapter writing and article assembly), or routes a follow-up request
to the separate native DeepAgents post-processing branch, and returns the
complete final state with ``thread_id`` attached. The source
``langgraph.json`` only declares the ``search_user`` test stub, so this
deployment keeps the production orchestrator and omits config/graph_id in the
manifest: this binding is the direct loader entrypoint.

Adaptations (reasoning, prompts, tools and model choices stay in the Agent):
- Input: text, exactly ``{'topic': text}``, or the topic field plus the
  optional native fields ``demand``, ``thread_id`` and ``is_lookup_outline``
  with their native defaults when absent. No demand text, session ID, outline
  feedback or answer is ever invented for a text Case.
- Output: the complete native final state dictionary (``thread_id``,
  ``status``, ``user_query``, ``outline_content``, ``chapter_content``,
  ``messages``, ``article_file_path``, ``error``, ...). Native ``status`` and
  ``error`` values are returned unchanged, and an ``is_lookup_outline`` run
  surfaces the native outline-review interrupt instead of approving it.
- Config: the public ``run`` method takes no config parameter, so callbacks,
  tags and metadata are published through LangChain's config context
  (``set_config_context``), which the nested native ``graph.ainvoke`` call
  inherits; the config object itself is never serialized or emptied.
  ``config['configurable']['thread_id']`` is forwarded as the native
  ``thread_id`` argument so the supplied Case thread identity survives instead
  of being replaced by a fresh UUID on every call.
- Resources: ``src.utils.logs`` evaluates ``Path(os.getenv('LOG_DIR'))`` at
  import time and native outputs (outline/article files, ``data/{user_id}``,
  Chroma storage) are working-directory relative, so each instance owns a
  private TemporaryDirectory workspace, points ``LOG_DIR`` and
  ``CHROMA_STORAGE_PATH`` into it when they are unset, and changes into it for
  the native run. ``close()``/``aclose()`` restore the working directory and
  remove the workspace; they are safe to repeat and after a failed load. LLM,
  embedding and Tavily endpoints and credentials are deployment-provided and
  never embedded here. The binding starts the image's pinned Elasticsearch
  distribution on loopback for the native hybrid retrieval path.
  Native exceptions propagate unchanged.

Example input: ``{'topic': 'Write a 1500-word article about adopting AI
coding assistants in small teams', 'demand': 'professional tone'}``.
Example output shape (all values come from the native run, never from this
binding): ``{'thread_id': '...', 'status': 'success', 'user_query': '...',
'depth_demand': '...', 'next_node': '...', 'outline_content': {...},
'chapter_content': [...], 'article_file_path': '...', 'messages': [...],
'error': None, ...}``.
"""

import asyncio
import builtins
import importlib
import os
import socket
import subprocess
import sys
import time
from collections.abc import Mapping
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import RLock

_INPUT_FIELDS = frozenset({'topic', 'demand', 'thread_id', 'is_lookup_outline'})


def _escape_native_format_template(template, field_names):
    """Make literal braces safe while preserving upstream ``{{ field }}`` slots."""
    tokens = {}
    for index, field in enumerate(field_names):
        token = f'\x00ABB_FORMAT_FIELD_{index}\x00'
        tokens[token] = field
        template = template.replace('{{ ' + field + ' }}', token)
        template = template.replace('{{' + field + '}}', token)
    template = template.replace('{', '{{').replace('}', '}}')
    for token, field in tokens.items():
        template = template.replace(token, '{' + field + '}')
    return template


def _install_prompt_format_compatibility():
    """Repair two pinned prompt loaders that mix Jinja slots with str.format.

    The upstream YAML contains literal JSON examples plus ``{{ field }}``
    variables. HeadAgent and MemoryManageAgent feed those strings to
    ``str.format``, which interprets the JSON object as a format field and
    raises KeyError before any Agent model call. Their other prompt consumers
    use direct replacement and are left untouched.
    """
    targets = (
        ('src.pipeline.agents.head_agent', 'head_prompt', ('user_query', 'depth_demand')),
        ('src.pipeline.agents.memory_manage_agent', 'memory_manage_prompt', ('history_messages',)),
    )
    for module_name, prompt_name, fields in targets:
        module = importlib.import_module(module_name)
        loader = module.load_prompt
        if getattr(loader, '_abb_brace_safe', False):
            continue

        def compatible_loader(name, _loader=loader, _name=prompt_name, _fields=fields):
            template = _loader(name)
            if name == _name:
                return _escape_native_format_template(template, _fields)
            return template

        compatible_loader._abb_brace_safe = True
        module.load_prompt = compatible_loader


def _install_elasticsearch_compatibility():
    """Drop one constructor option removed by upstream's locked ES client.

    OmniWriter locks ``elasticsearch==9.3.0`` but its ESClient still supplies
    the legacy alias ``timeout`` alongside ``request_timeout``. The former is
    rejected before any connection. Keep the native client method intact and
    remove only that retired duplicate keyword at its imported constructor.
    """
    module = importlib.import_module('src.core.es_client')
    constructor = module.Elasticsearch
    if getattr(constructor, '_abb_timeout_compatible', False):
        return

    def compatible_constructor(*args, **kwargs):
        kwargs.pop('timeout', None)
        return constructor(*args, **kwargs)

    compatible_constructor._abb_timeout_compatible = True
    module.Elasticsearch = compatible_constructor


def _wait_for_elasticsearch(process, timeout=90):
    """Wait until the embedded Elasticsearch HTTP socket accepts connections."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f'Elasticsearch exited before startup with code {process.returncode}'
            )
        try:
            connection = socket.create_connection(('127.0.0.1', 9200), timeout=0.25)
        except OSError:
            pass
        else:
            connection.close()
            return
        time.sleep(0.25)
    raise TimeoutError('Elasticsearch did not accept HTTP connections within 90 seconds')


def request_from_input(value):
    """Validate the current input against the native run() arguments.

    Args:
        value: Current text, exactly ``{'topic': text}``, or that topic field
            plus the optional native fields ``demand`` (string or None),
            ``thread_id`` (string or None) and ``is_lookup_outline`` (bool).
    Returns:
        ``(topic, demand, thread_id, is_lookup_outline)`` for the native
        ``WriterAgentOrchestrator.run`` lifecycle. Absent optional fields keep
        their native defaults (``None``, ``None``, ``False``).
    Raises:
        ValueError: Unknown fields or invalid types. The complete request text
            is preserved as the topic; it is never parsed or rewritten.
    """
    if isinstance(value, Mapping):
        unknown = set(value) - _INPUT_FIELDS
        if unknown:
            raise ValueError(f'Unsupported OmniWriter input fields: {sorted(unknown)}')
        if 'topic' not in value:
            raise ValueError('OmniWriter requires a topic field carrying the current request text')
        topic = value['topic']
        demand = value.get('demand')
        thread_id = value.get('thread_id')
        is_lookup_outline = value.get('is_lookup_outline', False)
    else:
        topic = value
        demand = None
        thread_id = None
        is_lookup_outline = False
    if not isinstance(topic, str) or not topic.strip():
        raise ValueError('OmniWriter topic must be the non-empty current request text')
    if demand is not None and not isinstance(demand, str):
        raise ValueError('OmniWriter demand must be a string or None')
    if thread_id is not None and (not isinstance(thread_id, str) or not thread_id.strip()):
        raise ValueError('OmniWriter thread_id must be a non-empty string or None')
    if not isinstance(is_lookup_outline, bool):
        raise ValueError('OmniWriter is_lookup_outline must be a boolean')
    return topic, demand, thread_id, is_lookup_outline


def _case_thread_id(config):
    """Return the Case thread identity supplied by the adapter, if any."""
    if not isinstance(config, Mapping):
        return None
    configurable = config.get('configurable')
    if isinstance(configurable, Mapping):
        thread_id = configurable.get('thread_id')
        if isinstance(thread_id, str) and thread_id.strip():
            return thread_id
    return None


def _load_orchestrator_class():
    """Import the native orchestrator, tolerating an uninstalled source root.

    ``uv sync`` installs the top-level ``src`` package declared in
    pyproject.toml; the fallback only adds an existing source root beside this
    binding when that installation is absent. Dependency import errors are
    re-raised unchanged.
    """
    root = Path(__file__).resolve().parents[1]
    for candidate in (root / 'agent', root):
        if (candidate / 'src' / 'pipeline' / 'orchestrator.py').is_file():
            if str(candidate) not in sys.path:
                sys.path.insert(0, str(candidate))
            break

    # Pinned upstream controller_agent.py uses MessageState in a runtime
    # annotation but omits its import. Supplying that type through builtins only
    # while Python executes the module is equivalent to its missing type import;
    # it does not replace a node, prompt, model, tool or execution result.
    from src.pipeline.state_model import MessageState

    missing = object()
    previous = getattr(builtins, 'MessageState', missing)
    builtins.MessageState = MessageState
    try:
        from src.pipeline.orchestrator import WriterAgentOrchestrator
        _install_prompt_format_compatibility()
        _install_elasticsearch_compatibility()
        return WriterAgentOrchestrator
    finally:
        if previous is missing:
            del builtins.MessageState
        else:
            builtins.MessageState = previous


class OmniWriterBinding:
    """Own one native orchestrator and its private writable workspace.

    One instance serves one Case and is reused for every Input; the native
    MemorySaver checkpoint keyed by the forwarded thread id provides the
    native session behavior. No additional history, memory or image
    generation behavior is added by this binding.
    """

    def __init__(self):
        self._native = None
        self._directory = None
        self._previous_cwd = None
        self._elasticsearch = None
        self._elasticsearch_log = None
        self._closed = False
        self._lock = RLock()

    def _load(self):
        """Construct the native orchestrator once, with a writable home.

        The workspace and the LOG_DIR / CHROMA_STORAGE_PATH defaults are
        established before the first ``src`` import because the native log
        module requires LOG_DIR at import time. A failed initialization
        releases everything created so far.
        """
        with self._lock:
            if self._closed:
                raise RuntimeError('OmniWriter binding is closed')
            if self._native is not None:
                return self._native
            self._directory = TemporaryDirectory(prefix='abb-omniwriter-')
            workspace = Path(self._directory.name)
            try:
                os.environ.setdefault('LOG_DIR', str(workspace / 'logs'))
                os.environ.setdefault('CHROMA_STORAGE_PATH', str(workspace / 'chroma'))
                os.environ.setdefault('ES_HOSTS', 'http://127.0.0.1:9200')
                os.environ.setdefault('ES_USERNAME', 'elastic')
                os.environ.setdefault('ES_PASSWORD', '')
                os.environ.setdefault('LANGSMITH_TRACING', 'false')
                os.environ.setdefault('LANGSMITH_API_KEY', '')
                os.environ.setdefault('LANGSMITH_PROJECT', 'OmniWriter')
                # controller_agent.py constructs its configurable secondary client
                # at import time. Point that native client at the same intercepted
                # endpoint/credential without embedding either value in the unit.
                os.environ.setdefault('SILICONFLOW_BASE_URL', os.environ.get('LLM_BASE_URL', ''))
                os.environ.setdefault('SILICONFLOW_API_KEY', os.environ.get('LLM_BASE_API_KEY', ''))
                self._previous_cwd = os.getcwd()
                os.chdir(workspace)
                es_data = workspace / 'elasticsearch-data'
                es_logs = workspace / 'elasticsearch-logs'
                es_data.mkdir()
                es_logs.mkdir()
                self._elasticsearch_log = open(
                    workspace / 'elasticsearch.log', 'w+b'
                )
                elasticsearch_env = os.environ.copy()
                # The bundled repository-s3 module otherwise probes the EC2
                # metadata address even though OmniWriter uses only a local
                # index. Keep that unrelated cloud lookup out of Case traffic.
                elasticsearch_env.setdefault('AWS_EC2_METADATA_DISABLED', 'true')
                # ABB gives the complete Case container 1 GiB. The image-level
                # 512 MiB heap plus Elasticsearch direct memory and OmniWriter's
                # Python process crosses that cgroup limit after the full graph
                # imports, killing Elasticsearch before RagTool is constructed.
                # The Case corpus is tiny, so a 256 MiB single-node heap is ample.
                elasticsearch_env['ES_JAVA_OPTS'] = '-Xms256m -Xmx256m'
                self._elasticsearch = subprocess.Popen(
                    [
                        '/opt/elasticsearch/bin/elasticsearch',
                        '-Ediscovery.type=single-node',
                        '-Expack.security.enabled=false',
                        '-Expack.security.http.ssl.enabled=false',
                        '-Expack.ml.enabled=false',
                        '-Expack.watcher.enabled=false',
                        '-Enetwork.host=127.0.0.1',
                        '-Ehttp.port=9200',
                        f'-Epath.data={es_data}',
                        f'-Epath.logs={es_logs}',
                        '-Eingest.geoip.downloader.enabled=false',
                    ],
                    stdout=self._elasticsearch_log,
                    stderr=subprocess.STDOUT,
                    cwd=workspace,
                    env=elasticsearch_env,
                )
                _wait_for_elasticsearch(self._elasticsearch)
                self._native = _load_orchestrator_class()()
            except BaseException:
                self.close()
                raise
            return self._native

    async def ainvoke(self, value, config=None):
        """Run the native article-generation or post-processing lifecycle.

        Args:
            value: Current text, exactly ``{'topic': text}``, or the topic plus
                the optional native ``demand``/``thread_id``/``is_lookup_outline``.
            config: LangChain RunnableConfig from the worker. The public native
                ``run`` takes no config parameter, so callbacks, tags and
                metadata are published through LangChain's config context
                (inherited by the nested native ``graph.ainvoke``), and
                ``configurable.thread_id`` is forwarded as the native
                ``thread_id`` argument. The config object is never serialized.
        Returns:
            The complete native final state dictionary with ``thread_id``
            attached, exactly as the upstream run lifecycle returns it; native
            ``status``/``error`` values are preserved and no answer is
            manufactured here.
        Raises:
            ValueError: Invalid input shape.
            RuntimeError: Invocation after close().
            Native exceptions (LLM, Tavily, Elasticsearch, DeepAgents, graph
                failures) propagate unchanged; errors are never converted into
                success-looking answers.
        """
        topic, demand, thread_id, is_lookup_outline = request_from_input(value)
        native = self._load()
        resolved_thread_id = thread_id or _case_thread_id(config)
        run_config = dict(config or {})
        from langchain_core.runnables.config import set_config_context

        with set_config_context(run_config):
            return await native.run(
                topic=topic,
                demand=demand,
                thread_id=resolved_thread_id,
                is_lookup_outline=is_lookup_outline,
            )

    def invoke(self, value, config=None):
        """Synchronous bridge for callers without a running event loop.

        Async callers must await ``ainvoke`` (BBA's async adapter does); this
        bridge fails fast when the current thread already runs an event loop,
        because asyncio.run refuses nested loops.
        """
        return asyncio.run(self.ainvoke(value, config))

    def close(self):
        """Restore the working directory and remove the owned workspace.

        Safe to repeat and callable after partial initialization. The native
        orchestrator's in-memory checkpoint state is dropped, its embedded
        Elasticsearch process is stopped, and the optional Langfuse handler
        gets a best-effort flush that never masks an execution result.
        """
        with self._lock:
            self._closed = True
            native, self._native = self._native, None
            try:
                if native is not None:
                    flush = getattr(getattr(native, 'langfuse', None), 'flush', None)
                    if callable(flush):
                        try:
                            flush()
                        except Exception:
                            pass
            finally:
                process, self._elasticsearch = self._elasticsearch, None
                if process is not None and process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait(timeout=5)
                log, self._elasticsearch_log = self._elasticsearch_log, None
                if log is not None:
                    log.close()
                previous, self._previous_cwd = self._previous_cwd, None
                directory, self._directory = self._directory, None
                if previous is not None:
                    try:
                        os.chdir(previous)
                    except OSError:
                        pass
                if directory is not None:
                    directory.cleanup()

    async def aclose(self):
        """Async cleanup path; all owned resources are synchronous."""
        self.close()


def create_graph():
    """Create one binding instance for one Case; no arguments are accepted.

    A fresh instance is returned on every call because it owns mutable
    checkpoint state and a private workspace directory.
    """
    return OmniWriterBinding()
