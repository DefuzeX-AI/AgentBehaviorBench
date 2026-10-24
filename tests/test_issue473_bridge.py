"""Zero-model transport tests; real Agent acceptance is a separate container run."""
import asyncio
import importlib.util
import json
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest
from acp import text_block

UNIT = Path(__file__).resolve().parents[1] / 'resources/agents/91-pydantic-deepagents'


def load_bridge():
    spec = importlib.util.spec_from_file_location('abb473_bridge', UNIT / 'bootstrap/bridge.py')
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class Conn:
    def __init__(self):
        self.updates = []
    async def session_update(self, **value):
        self.updates.append(value)


class NativeAPIFixture:
    """Record exact public-API calls; never used by the deployed bridge."""
    def __init__(self, error=None, wait=None):
        self.calls = []
        self.error, self.wait = error, wait
    async def run(self, text, **kwargs):
        self.calls.append((text, dict(kwargs)))
        if self.error:
            raise self.error
        if self.wait:
            await self.wait.wait()
        async def events():
            yield SimpleNamespace(event_kind='function_tool_call', part=SimpleNamespace(
                tool_call_id='native-call', tool_name='read_file', args={'path': 'actual.txt'}))
            yield SimpleNamespace(event_kind='function_tool_result', part=SimpleNamespace(
                tool_call_id='native-call', content={'actual': 'source-result'}, outcome='success'))
        await kwargs['event_stream_handler'](None, events())
        history = [*kwargs['message_history'], ('input', text), ('output', 'native-output')]
        return SimpleNamespace(output='native-output', all_messages=lambda: history)


def fixture(tmp_path, **native_options):
    bridge = load_bridge()
    agents, contexts, workspaces, deps = [], [], [], []
    def create(ctx):
        contexts.append(ctx); agent = NativeAPIFixture(**native_options); agents.append(agent); return agent
    def workspace(cwd):
        value = object(); workspaces.append((cwd, value)); return value
    def dependency():
        value = object(); deps.append(value); return value
    server = bridge.DeepAgentBridge(agent_factory=create, workspace_factory=workspace,
                                     deps_factory=dependency, model='openai-chat:glm-5.3-flash')
    server.on_connect(Conn())
    return server, agents, contexts, workspaces, deps


def test_run_uses_exact_native_factories_and_context_without_replacing_tools(tmp_path):
    async def check():
        server, agents, contexts, workspaces, deps = fixture(tmp_path)
        session = (await server.new_session(str(tmp_path))).session_id
        reply = await server.prompt([text_block('exact input')], session)
        text, options = agents[0].calls[0]
        assert text == 'exact input' and reply.stop_reason == 'end_turn'
        assert contexts[0].cwd == str(tmp_path) and contexts[0].model == 'openai-chat:glm-5.3-flash'
        assert options['deps'] is deps[0] and options['workspace'] is workspaces[0][1]
        assert set(options) == {'deps', 'workspace', 'message_history', 'event_stream_handler'}
        updates = [x['update'].model_dump(by_alias=True, exclude_none=True) for x in server.conn.updates]
        assert updates[0]['rawInput'] == {'path': 'actual.txt'}
        assert updates[1]['rawOutput'] == {'content': {'actual': 'source-result'}, 'outcome': 'success'}
        assert updates[1]['status'] == 'completed'
        assert updates[2]['content']['text'] == 'native-output'
    asyncio.run(check())


def test_history_continues_within_a_case_but_not_between_sessions(tmp_path):
    async def check():
        server, agents, *_ = fixture(tmp_path)
        one = (await server.new_session(str(tmp_path))).session_id
        two = (await server.new_session(str(tmp_path))).session_id
        await server.prompt([text_block('first')], one)
        await server.prompt([text_block('second')], one)
        await server.prompt([text_block('separate')], two)
        assert agents[1].calls[0][1]['message_history'] == [('input', 'first'), ('output', 'native-output')]
        assert agents[2].calls[0][1]['message_history'] == []
    asyncio.run(check())


def test_native_exception_is_not_returned_as_successful_agent_output(tmp_path):
    async def check():
        server, *_ = fixture(tmp_path, error=RuntimeError('real native exception'))
        session = (await server.new_session(str(tmp_path))).session_id
        with pytest.raises(RuntimeError, match='real native exception'):
            await server.prompt([text_block('input')], session)
        assert not server.conn.updates
        assert server.sessions[session].history == [] and server.sessions[session].task is None
    asyncio.run(check())


def test_cancellation_does_not_claim_end_turn_and_overlap_is_rejected(tmp_path):
    async def check():
        wait = asyncio.Event()
        server, *_ = fixture(tmp_path, wait=wait)
        session = (await server.new_session(str(tmp_path))).session_id
        task = asyncio.create_task(server.prompt([text_block('pending')], session))
        await asyncio.sleep(0)
        with pytest.raises(ValueError, match='already active'):
            await server.prompt([text_block('overlap')], session)
        await server.cancel(session)
        assert (await task).stop_reason == 'cancelled'
        assert not server.conn.updates and server.sessions[session].history == []
    asyncio.run(check())


@pytest.mark.parametrize('outcome,status', [('success','completed'),('failed','failed'),('denied','failed'),('interrupted','failed'),('retried','failed')])
def test_tool_outcome_comes_from_native_metadata_not_result_text(tmp_path, outcome, status):
    async def check():
        server, *_ = fixture(tmp_path)
        async def events():
            yield SimpleNamespace(event_kind='function_tool_result', part=SimpleNamespace(
                tool_call_id='original-id', content='Error is a literal in a file', outcome=outcome))
        await server._events('session', events())
        value = server.conn.updates[0]['update']
        assert value.status == status and value.raw_output == {'content': 'Error is a literal in a file', 'outcome': outcome}
    asyncio.run(check())


def test_no_fallback_model_external_mcp_or_missing_workspace(tmp_path):
    async def check():
        server, *_ = fixture(tmp_path)
        session = (await server.new_session(str(tmp_path))).session_id
        with pytest.raises(ValueError, match='without fallback'):
            await server.set_session_model('another-model', session)
        with pytest.raises(ValueError, match='MCP'):
            await server.new_session(str(tmp_path), mcp_servers=[{'name': 'not-configured'}])
        with pytest.raises(ValueError, match='existing absolute'):
            await server.new_session(str(tmp_path/'missing'))
        assert len(server.sessions) == 1
    asyncio.run(check())


def test_transport_uses_public_run_and_never_monkey_patches_native_source():
    text = (UNIT/'bootstrap/bridge.py').read_text()
    assert 'await agent.run(' in text and 'part = event.part' in text
    assert 'event.result' not in text and 'setattr(' not in text
    server = (UNIT/'bootstrap/server.py').read_text()
    assert 'from pydantic_deep import DeepAgentDeps, LocalWorkspace, create_deep_agent' in server
    assert 'DeepAgentACP' not in server.replace('# Same native confined per-run workspace as upstream DeepAgentACP._workspace_for.', '')
    assert 'context_discovery=True' in server and 'workspace=LocalWorkspace(ctx.cwd)' in server
