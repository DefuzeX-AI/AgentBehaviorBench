"""Host OntoCast's documented native LangGraph text-to-Turtle integration.

Source contract: examples/langgraph_subgraph.py, integrations/langgraph.py.
The documented native Fuseki backend runs Case-locally without vector retrieval. The
full native graph (conversion/chunking, extraction, critics, normalization and
validation) remains unchanged. Native text_in_turtle_out supplies both state
mappings. Each input is a complete new document, not a chat instruction/history.

The native OpenAI-compatible client uses the declared source-side endpoint;
ABB replacement interception owns the effective model/provider/credentials.
No model response, tool, native prompt or graph node is patched. The default
native settings apply except the documented local-store deployment and model
transport. No externally supplied ontology, database or embedding service is
assumed. Owned asynchronous resources stay on one loop until Case cleanup.
"""
from __future__ import annotations

import asyncio
import os
from collections.abc import Mapping
from pathlib import Path
import secrets
import tempfile
from urllib.request import ProxyHandler, build_opener


def _document(value):
    if isinstance(value, Mapping):
        if set(value) != {'message'}:
            raise ValueError('Supply text or exactly {"message": text}; no hidden native state overrides')
        value = value['message']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Supply a non-empty complete document as text')
    return value


class LocalFuseki:
    uri = 'http://127.0.0.1:3030'

    def __init__(self):
        self.auth = 'abb:' + secrets.token_urlsafe(24)
        self._process = None
        self._log = None

    async def start(self):
        workspace = Path('/home/agent/workspace')
        directory = Path(tempfile.mkdtemp(prefix='fuseki-', dir=workspace))
        self._log = (directory / 'server.log').open('wb')
        env = {**os.environ, 'FUSEKI_BASE': str(directory)}
        self._process = await asyncio.create_subprocess_exec(
            '/opt/java/openjdk/bin/java', '-Xms16m', '-Xmx128m',
            '-XX:ActiveProcessorCount=1', '-XX:MaxMetaspaceSize=128m',
            '-XX:ReservedCodeCacheSize=32m', '-Xss256k',
            '-Dlog4j.configurationFile=/opt/fuseki/log4j2.properties',
            '-cp', '/opt/fuseki/jena-fuseki-server-6.0.0.jar',
            'org.apache.jena.fuseki.main.cmds.FusekiServerCmd',
            '--localhost', '--port=3030', '--admin=' + self.auth,
            '--ping', cwd=directory,
            env=env, stdout=self._log, stderr=asyncio.subprocess.STDOUT,
        )
        opener = build_opener(ProxyHandler({}))

        def ready():
            try:
                with opener.open(self.uri + '/$/ping', timeout=1) as response:
                    return response.status == 200
            except OSError:
                return False

        for _ in range(120):
            if self._process.returncode is not None:
                raise RuntimeError('Case-local Fuseki exited; see its workspace server.log')
            if await asyncio.to_thread(ready):
                return
            await asyncio.sleep(0.5)
        raise TimeoutError('Case-local Fuseki did not become ready within 60 seconds')

    async def aclose(self):
        try:
            if self._process is not None and self._process.returncode is None:
                self._process.terminate()
                try:
                    await asyncio.wait_for(self._process.wait(), timeout=5)
                except TimeoutError:
                    self._process.kill()
                    await self._process.wait()
        finally:
            self._process = None
            if self._log is not None:
                self._log.close()
                self._log = None


class OntocastGraph:
    def __init__(self):
        self._tools = None
        self._store_service = None
        self._node = None
        self._loop = None
        self._runner = None
        self._closed = False

    async def _start(self):
        if self._closed:
            raise RuntimeError('OntoCast binding is closed')
        loop = asyncio.get_running_loop()
        if self._loop is not None and loop is not self._loop:
            raise RuntimeError('Use one event loop for invocation and cleanup')
        self._loop = loop
        if self._node is not None:
            return
        from ontocast import Config, ToolBox, make_ontocast_node, text_in_turtle_out
        from ontocast.config import LLMProvider


        deployment = Config.in_memory()
        self._store_service = LocalFuseki()
        deployment.tool_config.fuseki.uri = self._store_service.uri
        deployment.tool_config.fuseki.auth = self._store_service.auth
        llm = deployment.tool_config.llm_config
        llm.provider = LLMProvider.OPENAI
        llm.model_name = 'abb-runtime-selected'
        llm.base_url = 'https://api.openai.com/v1'
        llm.api_key = os.environ['OPENAI_API_KEY']
        try:
            await self._store_service.start()
            self._tools = await ToolBox.acreate(deployment)
            await self._tools.initialize()
            to_state, from_state = text_in_turtle_out()
            self._node = make_ontocast_node(
                self._tools, to_agent_state=to_state, from_agent_state=from_state,
            )
        except BaseException:
            await self.aclose()
            raise

    async def ainvoke(self, value, config=None):
        text = _document(value)
        await self._start()
        result = await self._node({'input': text}, config or {})
        ontology, facts = result['ontology_ttl'], result['facts_ttl']
        return {
            **result,
            'response': (
                '# Ontology (Turtle)\n```turtle\n' + ontology + '\n```\n'
                '# Facts (Turtle)\n```turtle\n' + facts + '\n```'
            ),
        }

    def _sync(self, operation):
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass
        else:
            raise RuntimeError('Use ainvoke/aclose inside an active event loop')
        if self._runner is None:
            self._runner = asyncio.Runner()
        return self._runner.run(operation())

    def invoke(self, value, config=None):
        return self._sync(lambda: self.ainvoke(value, config=config))

    async def aclose(self):
        if self._closed:
            return
        if self._loop is not None and self._loop is not asyncio.get_running_loop():
            raise RuntimeError('Cleanup must use the invocation event loop')
        self._closed = True
        self._node = None
        try:
            if self._tools is not None:
                tools, self._tools = self._tools, None
                await tools.aclose()
        finally:
            if self._store_service is not None:
                service, self._store_service = self._store_service, None
                await service.aclose()

    def close(self):
        try:
            self._sync(self.aclose)
        finally:
            if self._runner is not None:
                self._runner.close()
                self._runner = None


def create_graph():
    return OntocastGraph()
