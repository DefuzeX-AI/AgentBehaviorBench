from typing import Any


from langchain_core.messages import AIMessage

from ...classes import ResearchState
from ...prompts import NEWS_SCANNER_QUERY_PROMPT
from .base import BaseResearcher


class NewsScanner(BaseResearcher):
    def __init__(self) -> None:
        super().__init__()
        self.analyst_type = "news_analyzer"

    async def analyze(self, state: ResearchState):
        """Analyze news and yield events"""
        company = state.get('company', 'Unknown Company')
        
        # Generate search queries and yield events
        queries = []
        async for event in self.generate_queries(state, NEWS_SCANNER_QUERY_PROMPT):
            yield event
            if event.get("type") == "queries_complete":
                queries = event.get("queries", [])
        
        # Log subqueries
        subqueries_msg = "🔍 Subqueries for news analysis:\n" + "\n".join([f"• {query}" for query in queries])
        state.setdefault('messages', []).append(AIMessage(content=subqueries_msg))
        
        # Start with site scrape data
        news_data = dict[str, Any](state.get('site_scrape', {}))
        
        # Search and merge documents, yielding events
        documents = {}
        async for event in self.search_documents(state, queries):
            yield event
            if event.get("type") == "search_complete":
                documents = event.get("merged_docs", {})
        
        news_data.update(documents)
        
        # Update state
        completion_msg = f"📰 News Scanner found {len(news_data)} documents for {company}"
        state.setdefault('messages', []).append(AIMessage(content=completion_msg))
        state['news_data'] = news_data
        
        yield {"type": "analysis_complete", "data_type": "news_data", "count": len(news_data)}
        yield {'message': [completion_msg], 'news_data': news_data}

    async def run(self, state: ResearchState):
        """Run analysis and yield all events"""
        result = None
        async for event in self.analyze(state):
            yield event
            if "message" in event or "news_data" in event:
                result = event
        yield result or {} 