"""Run the original GPT Researcher with native keyless search/local embeddings."""
import asyncio
import json
import time
from threading import Lock
from pathlib import Path


class PubMedRequestGate:
    """Serialize native NCBI requests in this Case process, including failures.

    Each request finishes before the next 1.1-second cooldown starts. With at
    most three active Case workers this stays within the keyless 3 requests/s
    NCBI allowance. This gate does not retry or alter native responses.
    """
    def __init__(self, interval=1.1):
        self.interval = interval
        self.lock = Lock()
        self.next_request = 0.0

    def call(self, operation, *args, **kwargs):
        with self.lock:
            time.sleep(max(0.0, self.next_request - time.monotonic()))
            try:
                return operation(*args, **kwargs)
            finally:
                self.next_request = time.monotonic() + self.interval


_PUBMED_REQUESTS = PubMedRequestGate()


def query_from_messages(value):
    """Return an explicit query containing only this Case's supplied conversation.

    Args:
        value: {query: text} for observe or {messages: user/assistant list} for Kuma.
    Returns:
        Query text supplied to GPTResearcher without dropping previous turns.
    Raises:
        ValueError: Empty query, invalid roles or non-text conversation content.
    """
    if not isinstance(value, dict):
        raise ValueError('Expected query or messages object')
    if 'messages' not in value:
        query = value.get('query')
        if not isinstance(query, str) or not query.strip():
            raise ValueError('query must be non-empty text')
        return query
    messages = value['messages']
    if not isinstance(messages, list) or not messages:
        raise ValueError('messages must be non-empty')
    for message in messages:
        if (not isinstance(message, dict) or message.get('role') not in ('user', 'assistant')
                or not isinstance(message.get('content'), str)):
            raise ValueError('Expected text user/assistant conversation messages')
    if messages[-1]['role'] != 'user':
        raise ValueError('Current message must be from the user')
    if len(messages) == 1:
        return messages[0]['content']
    return ('Research the current user request in the context of this conversation. '
            'Previous assistant reports are prior discussion, not verified new sources.\n'
            + json.dumps(messages, ensure_ascii=False))


class ResearchGraph:
    def invoke(self, value, config=None, *, context=None):
        return asyncio.run(self.ainvoke(value, config, context=context))

    async def ainvoke(self, value, config=None, *, context=None):
        """Return the native Markdown report after real research and report writing.

        Args:
            value: Current Case conversation or a native query object.
            config: Process-local RunnableConfig used by model/search callbacks.
            context: Reserved deployment context; settings live in research.json.
        Returns:
            {answer: Markdown, sources: native source URLs}. Failures propagate.
        """
        from gpt_researcher import GPTResearcher
        from gpt_researcher.retrievers.pubmed_central.pubmed_central import PubMedCentralSearch
        from langchain_core.tools import StructuredTool

        run_config = config or {}

        class ObservedPubMed(PubMedCentralSearch):
            """Observe the actual native call; preserve its parameters and result."""
            def _search_articles(self, max_results):
                return _PUBMED_REQUESTS.call(super()._search_articles, max_results)

            def _fetch_full_text(self, article_id):
                return _PUBMED_REQUESTS.call(super()._fetch_full_text, article_id)

            def search(self, max_results=5):
                def search(query: str, max_results: int):
                    return PubMedCentralSearch.search(self, max_results=max_results)
                call = StructuredTool.from_function(search, name='pubmed_central_search',
                        description='Search PubMed Central and retrieve native article full text.')
                return call.invoke({'query': self.query, 'max_results': max_results}, config=run_config)

        researcher = GPTResearcher(query=query_from_messages(value), report_type='research_report',
                config_path=str(Path(__file__).with_name('research.json')), verbose=False,
                mcp_strategy='disabled')
        researcher.retrievers = [ObservedPubMed]
        researcher.cfg.llm_kwargs = dict(researcher.cfg.llm_kwargs,
                                        callbacks=run_config.get('callbacks'))
        await researcher.conduct_research()
        report = await researcher.write_report()
        if not isinstance(report, str) or not report.strip():
            raise RuntimeError('GPT Researcher returned an empty report')
        return {'answer': report, 'sources': researcher.get_source_urls()}

    def close(self):
        pass


def create_graph():
    """Expose the native Python researcher through one explicit LangGraph node."""
    from typing_extensions import TypedDict
    from langgraph.graph import StateGraph, START, END

    class State(TypedDict, total=False):
        query: str
        messages: list
        answer: str
        sources: list

    async def research(state, config):
        return await ResearchGraph().ainvoke(state, config=config)

    graph = StateGraph(State)
    graph.add_node('research', research)
    graph.add_edge(START, 'research')
    graph.add_edge('research', END)
    return graph.compile()
