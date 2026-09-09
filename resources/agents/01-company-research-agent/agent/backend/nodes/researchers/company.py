from typing import Any

from langchain_core.messages import AIMessage

from ...classes import ResearchState
from ...prompts import COMPANY_ANALYZER_QUERY_PROMPT
from .base import BaseResearcher


class CompanyAnalyzer(BaseResearcher):
    def __init__(self) -> None:
        super().__init__()
        self.analyst_type = "company_analyzer"

    async def analyze(self, state: ResearchState):
        """Analyze company and yield events"""
        company = state.get('company', 'Unknown Company')
        
        # Generate search queries and yield events
        queries = []
        async for event in self.generate_queries(state, COMPANY_ANALYZER_QUERY_PROMPT):
            yield event
            if event.get("type") == "queries_complete":
                queries = event.get("queries", [])
        
        # Log subqueries
        subqueries_msg = "🔍 Subqueries for company analysis:\n" + "\n".join([f"• {query}" for query in queries])
        state.setdefault('messages', []).append(AIMessage(content=subqueries_msg))
        
        # Start with site scrape data
        company_data = dict[str, Any](state.get('site_scrape', {}))
        
        # Search and merge documents, yielding events
        documents = {}
        async for event in self.search_documents(state, queries):
            yield event
            if event.get("type") == "search_complete":
                documents = event.get("merged_docs", {})
        
        company_data.update(documents)
        
        # Update state
        completion_msg = f"🏢 Company Analyzer found {len(company_data)} documents for {company}"
        state.setdefault('messages', []).append(AIMessage(content=completion_msg))
        state['company_data'] = company_data
        
        yield {"type": "analysis_complete", "data_type": "company_data", "count": len(company_data)}
        yield {'message': [completion_msg], 'company_data': company_data}

    async def run(self, state: ResearchState):
        """Run analysis and yield all events"""
        result = None
        async for event in self.analyze(state):
            yield event
            if "message" in event or "company_data" in event:
                result = event
        yield result or {} 