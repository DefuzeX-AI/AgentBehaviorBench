"""Container-only offline fixture; production binding never substitutes services."""
import asyncio
import json
from pathlib import Path
from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.messages import AIMessage
from agentbench.runtime.agentcontainer.worker import execute
from agentbench.runtime.agentcontainer.session import AgentSession
from agentbench.sdk.common.input_binding import InputBinding
from importlib import import_module
native_graph = import_module('react_agent.graph')
native_tools = import_module('react_agent.tools')

seen, searches = [], []

class Model(FakeMessagesListChatModel):
    def bind_tools(self, tools, **kwargs):
        return self

    def _generate(self, messages, *args, **kwargs):
        seen.append(messages)
        return super()._generate(messages, *args, **kwargs)

class Search:
    def __init__(self, *, max_results):
        assert max_results == 5

    async def ainvoke(self, value):
        searches.append(value)
        return {'results': [{'title': 'Offline fixture', 'url': 'https://example.test', 'content': 'Fixture evidence.'}]}

model = Model(responses=[
    AIMessage(content='', tool_calls=[{'name': 'search', 'args': {'query': 'fixture question'}, 'id': 'search-1'}]),
    AIMessage(content='First answer from fixture evidence.'),
    AIMessage(content='Follow-up answer with explicit history.'),
])

def load_model(name):
    assert name == 'openai/gpt-4.1-mini'
    return model

native_graph.load_chat_model = load_model
native_tools.TavilySearch = Search

async def main():
    base = Path('/tmp/react-checks')
    base.mkdir()
    session = AgentSession()
    conversation = InputBinding.from_file(Path("/opt/agent/evaluation/input-contract.json")).new_conversation()
    for step in (1, 2):
        output = base / str(step)
        output.mkdir()
        request = base / f'request-{step}.json'
        value = conversation.prepare('fixture question' if step == 1 else 'follow-up')
        request.write_text(json.dumps({'schema': 'abb.invocation.v1', 'run_id': f'react-{step}',
            'session_id': 'case-fixture', 'agent_id': 'react-agent', 'framework': 'langgraph', 'input': value}))
        status = await execute(Path('/opt/agent'), request, output, session=session)
        result = json.loads((output / 'result.json').read_text())
        assert status == 0, result
        conversation.commit(result)
        assert json.loads((output / 'otel-status.json').read_text())['status'] == 'complete'
        assert (output / 'framework.jsonl').stat().st_size > 0
    await session.aclose()
    assert session.snapshot()['adapter_initializations'] == 1
    assert session.snapshot()['invocations'] == 2
    assert session.snapshot()['closed'] is True
    assert len(searches) == 1 and len(seen) == 3
    assert any(m.content == 'First answer from fixture evidence.' for m in seen[-1])
    assert any(m.type == 'tool' for m in seen[-1])
    print(json.dumps({'status':'passed', 'llm_calls':len(seen), 'search_calls':len(searches),
        'automatic_history':True, 'adapter_initializations':1, 'otel':'complete', 'production_network_calls':0}))

asyncio.run(main())
