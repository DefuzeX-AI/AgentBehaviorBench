import logging
from typing import Dict
from urllib.parse import urljoin, urlparse

from langchain_core.messages import AIMessage

from ..classes import ResearchState
from ..classes.state import job_status
from ..utils.references import process_references_from_search_results

logger = logging.getLogger(__name__)

class Curator:
    def __init__(self) -> None:
        self.relevance_threshold = 0.4
        logger.info(f"Curator initialized with relevance threshold: {self.relevance_threshold}")

    def evaluate_documents(self, docs: list, context: Dict[str, str]) -> list:
        """Evaluate documents based on Tavily's scoring."""
        if not docs:
            return []

        logger.info(f"Evaluating {len(docs)} documents")
        
        evaluated_docs = []
        try:
            # Evaluate each document using Tavily's score
            for doc in docs:
                try:
                    # Ensure score is a valid float
                    tavily_score = float(doc.get('score', 0))  # Default to 0 if no score
                    
                    # Always keep company website data regardless of score (first-party information)
                    is_company_website = doc.get('source') == 'company_website'
                    
                    # Keep documents with good Tavily score or company website data
                    if tavily_score >= self.relevance_threshold or is_company_website:
                        reason = "company website" if is_company_website else f"score {tavily_score:.4f}"
                        logger.info(f"Document kept ({reason}) for '{doc.get('title', 'No title')}')")
                        
                        evaluated_doc = {
                            **doc,
                            "evaluation": {
                                "overall_score": tavily_score,  # Store as float
                                "query": doc.get('query', '')
                            }
                        }
                        evaluated_docs.append(evaluated_doc)
                    else:
                        logger.info(f"Document below threshold with score {tavily_score:.4f} for '{doc.get('title', 'No title')}'")
                except (ValueError, TypeError) as e:
                    logger.warning(f"Error processing score for document: {e}")
                    continue
                    
        except Exception as e:
            logger.error(f"Error during document evaluation: {e}")
            return []

        # Sort evaluated docs by score before returning
        evaluated_docs.sort(key=lambda x: float(x['evaluation']['overall_score']), reverse=True)
        logger.info(f"Returning {len(evaluated_docs)} evaluated documents")
        
        return evaluated_docs

    async def curate_data(self, state: ResearchState) -> ResearchState:
        """Curate all collected data based on Tavily scores."""
        company = state.get('company', 'Unknown Company')
        job_id = state.get('job_id')
        logger.info(f"Starting curation for company: {company}, job_id={job_id}")

        industry = state.get('industry', 'Unknown')
        context = {
            "company": company,
            "industry": industry,
            "hq_location": state.get('hq_location', 'Unknown')
        }

        msg = [f"🔍 Curating research data for {company}"]
        
        data_types = {
            'financial_data': ('💰 Financial', 'financial'),
            'news_data': ('📰 News', 'news'),
            'industry_data': ('🏭 Industry', 'industry'),
            'company_data': ('🏢 Company', 'company')
        }

        # Process each data type
        for data_field, (emoji, doc_type) in data_types.items():
            data = state.get(data_field, {})
            if not data:
                continue

            # Filter and normalize URLs
            unique_docs = {}
            for url, doc in data.items():
                try:
                    parsed = urlparse(url)
                    if not parsed.scheme:
                        url = urljoin('https://', url)
                    clean_url = parsed._replace(query='', fragment='').geturl()
                    if clean_url not in unique_docs:
                        doc['url'] = clean_url
                        doc['doc_type'] = doc_type
                        unique_docs[clean_url] = doc
                except Exception:
                    continue

            docs = list(unique_docs.values())
            msg.append(f"\n{emoji}: Found {len(docs)} documents")
            
            evaluated_docs = self.evaluate_documents(docs, context)
            
            # Emit curation event with total count
            if job_id:
                try:
                    if job_id in job_status:
                        job_status[job_id]["events"].append({
                            "type": "curation",
                            "category": doc_type,
                            "total": len(evaluated_docs) if evaluated_docs else 0,
                            "message": f"Curating {doc_type} documents"
                        })
                except Exception as e:
                    logger.error(f"Error appending curation event: {e}")

            if not evaluated_docs:
                msg.append("  ⚠️ No relevant documents found")
                continue

            # Filter and sort by Tavily score
            relevant_docs = {doc['url']: doc for doc in evaluated_docs}
            sorted_items = sorted(relevant_docs.items(), key=lambda item: item[1]['evaluation']['overall_score'], reverse=True)
            
            # Limit to top 30 documents per category
            if len(sorted_items) > 30:
                sorted_items = sorted_items[:30]
            relevant_docs = dict(sorted_items)

            if relevant_docs:
                msg.append(f"  ✓ Kept {len(relevant_docs)} relevant documents")
                logger.info(f"Kept {len(relevant_docs)} documents for {doc_type} with scores above threshold")
            else:
                msg.append("  ⚠️ No documents met relevance threshold")
                logger.info(f"No documents met relevance threshold for {doc_type}")

            # Store curated documents in state
            state[f'curated_{data_field}'] = relevant_docs
            
        # Process references using the references module
        top_reference_urls, reference_titles, reference_info = process_references_from_search_results(state)
        logger.info(f"Selected top {len(top_reference_urls)} references for the report")
        
        # Update state with references and their titles
        state.setdefault('messages', []).append(AIMessage(content="\n".join(msg)))
        state['references'] = top_reference_urls
        state['reference_titles'] = reference_titles
        state['reference_info'] = reference_info

        return state

    async def run(self, state: ResearchState) -> ResearchState:
        return await self.curate_data(state)
