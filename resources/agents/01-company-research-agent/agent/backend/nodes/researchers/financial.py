from langchain_core.messages import AIMessage

from ...classes import ResearchState
from ...prompts import FINANCIAL_ANALYZER_QUERY_PROMPT
from .base import BaseResearcher


class FinancialAnalyst(BaseResearcher):
    def __init__(self) -> None:
        super().__init__()
        self.analyst_type = "financial_analyzer"
    
    async def analyze(self, state: ResearchState):
        """Analyze financials and yield events"""
        company = state.get('company', 'Unknown Company')
        
        # Generate search queries and yield events
        queries = []
        async for event in self.generate_queries(state, FINANCIAL_ANALYZER_QUERY_PROMPT):
            yield event
            if event.get("type") == "queries_complete":
                queries = event.get("queries", [])
        
        # Log subqueries
        subqueries_msg = "🔍 Subqueries for financial analysis:\n" + "\n".join([f"• {query}" for query in queries])
        state.setdefault('messages', []).append(AIMessage(content=subqueries_msg))
        
        # Start with site scrape data
        financial_data = dict(state.get('site_scrape', {}))
        
        # Search and merge documents, yielding events
        documents = {}
        async for event in self.search_documents(state, queries):
            yield event
            if event.get("type") == "search_complete":
                documents = event.get("merged_docs", {})
        
        financial_data.update(documents)
        
        # Update state
        completion_msg = f"💰 Financial Analyst found {len(financial_data)} documents for {company}"
        state.setdefault('messages', []).append(AIMessage(content=completion_msg))
        state['financial_data'] = financial_data
        
        yield {"type": "analysis_complete", "data_type": "financial_data", "count": len(financial_data)}
        yield {'message': [completion_msg], 'financial_data': financial_data}

    async def run(self, state: ResearchState):
        """Run analysis and yield all events"""
        result = None
        async for event in self.analyze(state):
            yield event
            if "message" in event or "financial_data" in event:
                result = event
        yield result or {}