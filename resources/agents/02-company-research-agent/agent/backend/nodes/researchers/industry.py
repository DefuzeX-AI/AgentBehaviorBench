from langchain_core.messages import AIMessage

from ...classes import ResearchState
from ...prompts import INDUSTRY_ANALYZER_QUERY_PROMPT
from .base import BaseResearcher


class IndustryAnalyzer(BaseResearcher):
    def __init__(self) -> None:
        super().__init__()
        self.analyst_type = "industry_analyzer"

    async def analyze(self, state: ResearchState):
        """Analyze industry and yield events"""
        company = state.get('company', 'Unknown Company')
        industry = state.get('industry', 'Unknown Industry')
        
        # Generate search queries and yield events
        queries = []
        async for event in self.generate_queries(state, INDUSTRY_ANALYZER_QUERY_PROMPT):
            yield event
            if event.get("type") == "queries_complete":
                queries = event.get("queries", [])
        
        # Log subqueries
        subqueries_msg = "🔍 Subqueries for industry analysis:\n" + "\n".join([f"• {query}" for query in queries])
        state.setdefault('messages', []).append(AIMessage(content=subqueries_msg))
        
        # Start with site scrape data
        industry_data = dict(state.get('site_scrape', {}))
        
        # Search and merge documents, yielding events
        documents = {}
        async for event in self.search_documents(state, queries):
            yield event
            if event.get("type") == "search_complete":
                documents = event.get("merged_docs", {})
        
        industry_data.update(documents)
        
        # Update state
        completion_msg = f"🏭 Industry Analyzer found {len(industry_data)} documents for {company} in {industry}"
        state.setdefault('messages', []).append(AIMessage(content=completion_msg))
        state['industry_data'] = industry_data
        
        yield {"type": "analysis_complete", "data_type": "industry_data", "count": len(industry_data)}
        yield {'message': [completion_msg], 'industry_data': industry_data}

    async def run(self, state: ResearchState):
        """Run analysis and yield all events"""
        result = None
        async for event in self.analyze(state):
            yield event
            if "message" in event or "industry_data" in event:
                result = event
        yield result or {} 