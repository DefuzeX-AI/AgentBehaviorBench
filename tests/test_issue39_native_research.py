"""Mixed-suite GPT regressions: native writer policy and task-only inputs.

The pinned upstream prompt selector/report generator run unchanged. Model and
research transports are offline doubles; these checks do not prove an actual
model follows the limit, finds the right paper, or supplies correct citations.
"""
import asyncio
import importlib.util
import json
import logging
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace

import pytest


ROOT = Path(__file__).resolve().parents[1]
UNIT = ROOT / 'resources/agents/04-gpt-researcher'


def load_file(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def native_writer(monkeypatch):
    """Load real upstream generation/prompts without initializing its providers."""
    source = UNIT / 'agent/gpt_researcher'
    package = '_native_research_regression'
    # Isolate imports from the real package initializer, which loads unrelated
    # providers and optional dependencies. Prompt generation itself is native.
    for suffix, directory in [('', source), ('.actions', source / 'actions'),
                              ('.utils', source / 'utils')]:
        module = ModuleType(package + suffix)
        module.__path__ = [str(directory)]
        monkeypatch.setitem(sys.modules, module.__name__, module)
    config = ModuleType(package + '.config')
    config.__path__ = []
    config.Config = type('Config', (), {})
    monkeypatch.setitem(sys.modules, config.__name__, config)
    monkeypatch.setitem(sys.modules, package + '.config.config', config)
    captured = []
    response = ' '.join(['Untruncated'] * 620) + '\n[Source](https://example.org/paper)'

    async def completion(**kwargs):
        captured.append(kwargs)
        return response

    monkeypatch.setitem(sys.modules, package + '.utils.llm',
                        SimpleNamespace(create_chat_completion=completion))
    monkeypatch.setitem(sys.modules, package + '.utils.logger',
                        SimpleNamespace(get_formatted_logger=logging.getLogger))
    try:
        module = load_file(package + '.actions.report_generation',
                           source / 'actions/report_generation.py')
        cfg = SimpleNamespace(total_words=500, report_format='markdown', language='english',
                              smart_llm_model='offline', smart_llm_provider='offline',
                              smart_token_limit=3000, llm_kwargs={})

        async def generate(query, context, custom_prompt=''):
            return await module.generate_report(
                query=query, context=context, agent_role_prompt='Biomedical researcher',
                report_type='research_report', tone=None, report_source='web',
                websocket=None, cfg=cfg, custom_prompt=custom_prompt)

        yield SimpleNamespace(generate=generate, calls=captured, response=response)
    finally:
        # Child imports made by Python itself are not monkeypatch-managed.
        for name in list(sys.modules):
            if name.startswith(package + '.') and name not in {
                package + '.actions', package + '.utils', package + '.config',
                package + '.config.config', package + '.utils.llm', package + '.utils.logger',
            }:
                sys.modules.pop(name, None)


def test_native_writer_replaces_minimum_prompt_and_keeps_research_context(native_writer):
    """Reproduce the old >=500 instruction, then inspect actual new model input."""
    binding = load_file('gpt_binding_writer', UNIT / 'bindings/research.py')
    query = 'Summarize biomedical evidence in fewer than 200 words.'
    evidence = ['Title: Actual paper\nSource: https://example.org/paper\nObserved study text.']
    asyncio.run(native_writer.generate(query, evidence))
    original = native_writer.calls[-1]['messages'][-1]['content']
    assert 'at least 500 words' in original
    assert 'as long as you can' in original

    output = asyncio.run(native_writer.generate(query, evidence, binding.report_prompt(query)))
    delivered = native_writer.calls[-1]['messages'][-1]['content']
    assert 'at most 500 words in total, including references' in delivered
    assert 'respect a shorter limit if requested' in delivered
    assert 'at least 500 words' not in delivered
    assert 'as long as you can' not in delivered
    assert query in delivered and evidence[0].replace('\n', '\\n') in delivered
    assert output == native_writer.response  # Over-limit response stays visible to Judge.


def test_current_task_report_uses_public_custom_prompt_without_replaying_history(monkeypatch, native_writer):
    binding = load_file('gpt_binding_session', UNIT / 'bindings/research.py')
    tasks = []

    class Researcher:
        def __init__(self, **kwargs):
            self.query = kwargs['query']
            self.cfg = SimpleNamespace(llm_kwargs={})
            self.context = ['Native research context for ' + self.query]
            tasks.append(self)

        async def conduct_research(self):
            pass

        async def write_report(self, *, custom_prompt):
            return await native_writer.generate(self.query, self.context, custom_prompt)

        def get_source_urls(self):
            return []

        def get_research_sources(self):
            return [{'url': 'https://example.org/paper'}]

    monkeypatch.setitem(sys.modules, 'gpt_researcher', SimpleNamespace(GPTResearcher=Researcher))
    monkeypatch.setitem(sys.modules, 'gpt_researcher.retrievers.pubmed_central.pubmed_central',
                        SimpleNamespace(PubMedCentralSearch=type('Search', (), {})))
    # The task helper still receives only its current question. The session
    # binding separately routes later Inputs to the native report-chat API.
    graph = binding.ResearchGraph()
    first = asyncio.run(graph.ainvoke({'query': 'Remember ONLY ALPHA'}))
    second = asyncio.run(graph.ainvoke({'query': 'What paper did we discuss?'}))
    assert len(tasks) == 2 and tasks[0] is not tasks[1]
    assert [task.query for task in tasks] == ['Remember ONLY ALPHA', 'What paper did we discuss?']
    last_model_input = native_writer.calls[-1]['messages'][-1]['content']
    assert 'ONLY ALPHA' not in last_model_input
    assert 'Untruncated' not in last_model_input
    assert first['answer'] == second['answer'] == native_writer.response
    assert second['sources'] == ['https://example.org/paper']


def test_deployed_profile_and_configuration_separate_report_limit_from_native_chat():
    config = json.loads((UNIT / 'bindings/research.json').read_text())
    profile = (UNIT / 'requirement.md').read_text()
    assert 'TOTAL_WORDS' not in config
    assert 'native chat endpoint' in profile
    assert 'Later responses use the original chat prompt' in profile
    assert 'not an output truncation or a guaranteed word-count limit' in profile
