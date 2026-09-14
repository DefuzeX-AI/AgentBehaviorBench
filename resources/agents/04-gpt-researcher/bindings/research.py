"""Run the original GPT Researcher with native keyless search/local embeddings."""
import asyncio
import importlib.util
import json
import os
import sys
import time
from threading import Lock
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4


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
_APP_IMPORT_LOCK = Lock()


def search_pubmed_ids(retriever, max_results):
    """Use NCBI's GET/form-POST equivalents with the native search parameters.

    Args:
        retriever: Native PubMedCentralSearch instance holding query/db/settings.
        max_results: Requested article count, forwarded without modification.
    Returns:
        Native article-ID list, [] for an unexpected JSON envelope, or None on
        HTTP failure. The caller retains native full-text fetching and parsing.

    Select POST before sending URLs over 2000 encoded bytes; never retry a failed
    GET, truncate the query, or patch the process-wide requests implementation.
    """
    import requests

    term = (f'{retriever.query} AND (ffrft[filter] OR pmc[filter])'
            if retriever.db_type == 'pubmed' else retriever.query)
    params = {'db': retriever.db_type, 'term': term, 'retmax': max_results,
              'api_key': retriever.api_key, **retriever.params}
    url = retriever.base_search_url
    prepared_url = requests.Request('GET', url, params=params).prepare().url
    try:
        response = (requests.post(url, data=params) if len(prepared_url.encode()) > 2000
                    else requests.get(url, params=params))
        response.raise_for_status()
        data = response.json()
        result = data.get('esearchresult') if isinstance(data, dict) else None
        ids = result.get('idlist') if isinstance(result, dict) else None
        return ids if isinstance(ids, list) else []
    except requests.RequestException as exc:
        # Avoid printing a long request URL or its query/API-key parameters.
        status = exc.response.status_code if exc.response is not None else None
        print(f'PubMed search failed: {type(exc).__name__}, HTTP {status}')
        return None


def query_from_input(value):
    """Extract the current research question without adding conversation history.

    Args:
        value: Current text Input or the native {query: text} request object.
    Returns:
        The original query text, unchanged, for native research and search.
    Raises:
        ValueError: Empty/non-text query or a synthetic conversation envelope.
    """
    if isinstance(value, dict) and 'messages' in value:
        raise ValueError('Supply the current query, not a messages history')
    query = value.get('query') if isinstance(value, dict) else value
    if not isinstance(query, str) or not query.strip():
        raise ValueError('query must be non-empty text')
    return query


def report_prompt(query):
    """Build the deployment's instructions for the native report writer.

    Args:
        query: Original current research question; no previous turns or reports.
    Returns:
        A custom_prompt accepted by GPTResearcher.write_report(). The upstream
        writer adds its research context. This replaces its default minimum-word
        prompt; it requests a maximum without truncating the generated report.
    """
    return (
        'Write a biomedical literature research answer in Markdown to the current '
        'request below. Use at most 500 words in total, including references, and '
        'respect a shorter limit if requested. There is no minimum word count.\n'
        'Base factual claims on the supplied PubMed Central research context. '
        'Use a clear structure and cite substantive claims, figures and quotes '
        'with inline hyperlinks to sources in that context. Include a reference '
        'list of the sources used.\n'
        'Current request (JSON string):\n' + json.dumps(query, ensure_ascii=False)
    )


class ResearchGraph:
    def invoke(self, value, config=None, *, context=None):
        return asyncio.run(self.ainvoke(value, config, context=context))

    async def ainvoke(self, value, config=None, *, context=None):
        """Return the native Markdown report after real research and report writing.

        Args:
            value: Current research question as text or a native query object.
            config: Process-local RunnableConfig used by model/search callbacks.
            context: Reserved deployment context; settings live in research.json.
        Returns:
            {answer: Markdown, sources: native source URLs}. Failures propagate.
        """
        from gpt_researcher import GPTResearcher
        from gpt_researcher.retrievers.pubmed_central.pubmed_central import PubMedCentralSearch
        from langchain_core.tools import StructuredTool

        run_config = config or {}
        query = query_from_input(value)

        class ObservedPubMed(PubMedCentralSearch):
            """Observe native search terms without rewriting the input query."""

            def _search_articles(self, max_results):
                return _PUBMED_REQUESTS.call(search_pubmed_ids, self, max_results)

            def _fetch_full_text(self, article_id):
                return _PUBMED_REQUESTS.call(super()._fetch_full_text, article_id)

            def search(self, max_results=5):
                def search(query: str, max_results: int):
                    return PubMedCentralSearch.search(self, max_results=max_results)
                call = StructuredTool.from_function(search, name='pubmed_central_search',
                        description='Search PubMed Central and retrieve native article full text.')
                return call.invoke({'query': self.query, 'max_results': max_results}, config=run_config)

        researcher = GPTResearcher(query=query, report_type='research_report',
                config_path=str(Path(__file__).with_name('research.json')), verbose=False,
                mcp_strategy='disabled')
        researcher.retrievers = [ObservedPubMed]
        researcher.cfg.llm_kwargs = dict(researcher.cfg.llm_kwargs,
                                        callbacks=run_config.get('callbacks'))
        await researcher.conduct_research()
        # Public upstream customization API; TOTAL_WORDS in the default prompt
        # is a minimum, so it cannot implement this deployment's maximum.
        report = await researcher.write_report(custom_prompt=report_prompt(query))
        if not isinstance(report, str) or not report.strip():
            raise RuntimeError('GPT Researcher returned an empty report')
        # get_source_urls() contains scraped pages only. Native full-text
        # retrievers register their URLs in get_research_sources() instead.
        urls = [*researcher.get_source_urls(),
                *(source.get('url') for source in researcher.get_research_sources()
                  if isinstance(source, dict))]
        return {'answer': report, 'sources': list(dict.fromkeys(
            url for url in urls if isinstance(url, str) and url))}

    def close(self):
        pass


class NativeReportAPI:
    """Transport to one unchanged native app with a private native ReportStore.

    The original app owns persistence and chat history. Its supported
    REPORT_STORE_PATH environment setting is read only during app construction;
    the temporary override is restored before any asynchronous work starts.
    """
    def __init__(self):
        self.directory = TemporaryDirectory(prefix='gpt-native-report-')
        self.module_name = '_gpt_report_' + uuid4().hex
        self.module = None
        source = Path(__file__).resolve().parents[1] / 'agent/backend/server/app.py'
        try:
            spec = importlib.util.spec_from_file_location(self.module_name, source)
            module = importlib.util.module_from_spec(spec)
            # FastAPI/Pydantic resolve route annotations through sys.modules.
            sys.modules[self.module_name] = module
            with _APP_IMPORT_LOCK:
                previous = os.environ.get('REPORT_STORE_PATH')
                os.environ['REPORT_STORE_PATH'] = str(Path(self.directory.name) / 'reports.json')
                try:
                    spec.loader.exec_module(module)
                finally:
                    if previous is None:
                        os.environ.pop('REPORT_STORE_PATH', None)
                    else:
                        os.environ['REPORT_STORE_PATH'] = previous
            self.module = module
        except BaseException:
            self.close()
            raise

    async def post(self, path, payload):
        """Send one native API request; preserve native errors as failures."""
        import httpx
        if self.module is None:
            raise RuntimeError('Native report API is closed')
        # In-process ASGI transport opens no listening socket or remote endpoint.
        # These routes initialize at import; the web-server lifespan only mounts
        # output/static directories, which research/report chat does not require.
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=self.module.app),
                                     base_url='http://native-report', trust_env=False) as client:
            response = await client.post(path, json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, dict) or data.get('success') is not True:
            raise RuntimeError('Native report API did not complete the request')
        return data

    def close(self):
        self.module = None
        sys.modules.pop(self.module_name, None)
        self.directory.cleanup()


class ResearchSession:
    """Follow the native UI's research, save-report, report-chat workflow.

    One instance belongs to one Case. It holds only a native app transport and
    opaque report ID. Native ReportStore and ChatAgentWithMemory own the report,
    chat history and report retrieval; this binding never reads or builds them.
    """
    def __init__(self):
        from typing_extensions import TypedDict
        from langgraph.graph import StateGraph, START, END

        self._api = None
        self._report_id = None
        self._closed = False

        class State(TypedDict, total=False):
            query: str
            answer: str
            sources: list
            metadata: dict | None
            report_id: str

        async def research(state, config):
            return await self._run_current(query_from_input(state), config)

        graph = StateGraph(State)
        graph.add_node('research', research)
        graph.add_edge(START, 'research')
        graph.add_edge('research', END)
        # The real node supplies native LangChain callback context through ASGI.
        self._graph = graph.compile()

    async def _run_current(self, query, config):
        if self._closed:
            raise RuntimeError('Research session is closed')
        if self._api is None:
            self._api = NativeReportAPI()
        if self._report_id is None:
            result = await ResearchGraph().ainvoke({'query': query}, config=config)
            report_id = uuid4().hex
            saved = await self._api.post('/api/reports',
                {'id': report_id, 'question': query, 'answer': result['answer']})
            if saved.get('id') != report_id:
                raise RuntimeError('Native report API returned a different report ID')
            self._report_id = report_id
            return {**result, 'report_id': report_id}

        data = await self._api.post(f'/api/reports/{self._report_id}/chat',
                                    {'role': 'user', 'content': query})
        response = data.get('response')
        answer = response.get('content') if isinstance(response, dict) else None
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError('Native report chat returned an empty response')
        return {'answer': answer, 'metadata': response.get('metadata'),
                'report_id': self._report_id}

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config))

    async def ainvoke(self, value, config=None):
        """Deliver only the current question; native APIs handle session state."""
        return await self._graph.ainvoke({'query': query_from_input(value)}, config=config)

    def close(self):
        self._closed = True
        self._report_id = None
        if self._api is not None:
            self._api.close()
            self._api = None


def create_graph():
    """Create one native research/report-chat session for the Case lifetime."""
    return ResearchSession()
