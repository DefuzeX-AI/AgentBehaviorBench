import logging
import os
from typing import Dict

from langchain_core.messages import AIMessage
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

from ..classes import ResearchState
from ..classes.state import job_status
from ..utils.references import format_references_section
from ..prompts import (
    EDITOR_SYSTEM_MESSAGE,
    COMPILE_CONTENT_PROMPT,
    CONTENT_SWEEP_SYSTEM_MESSAGE,
    CONTENT_SWEEP_PROMPT
)

logger = logging.getLogger(__name__)

class Editor:
    """Compiles individual section briefings into a cohesive final report."""
    
    def __init__(self) -> None:
        openai_key = os.getenv("OPENAI_API_KEY")
        if not openai_key:
            raise ValueError("OPENAI_API_KEY environment variable is not set")
        
        # Configure LangChain ChatOpenAI
        self.llm = ChatOpenAI(
            model="gpt-4o",
            temperature=0,
            streaming=True,
            api_key=openai_key
        )
        
        # Initialize context dictionary
        self.context = {
            "company": "Unknown Company",
            "industry": "Unknown",
            "hq_location": "Unknown"
        }

    async def compile_briefings(self, state: ResearchState) -> ResearchState:
        """Compile individual briefing categories from state into a final report."""
        company = state.get('company', 'Unknown Company')
        job_id = state.get('job_id')
        
        # Update context with values from state
        self.context = {
            "company": company,
            "industry": state.get('industry', 'Unknown'),
            "hq_location": state.get('hq_location', 'Unknown')
        }
        
        msg = [f"📑 Compiling final report for {company}..."]
        
        # Emit report compilation start event
        if job_id:
            try:
                if job_id in job_status:
                    job_status[job_id]["events"].append({
                        "type": "report_compilation",
                        "message": f"Compiling final report for {company}"
                    })
            except Exception as e:
                logger.error(f"Error appending report_compilation event: {e}")
        
        # Pull individual briefings from dedicated state keys
        briefing_keys = {
            'company': 'company_briefing',
            'industry': 'industry_briefing',
            'financial': 'financial_briefing',
            'news': 'news_briefing'
        }

        individual_briefings = {}
        for category, key in briefing_keys.items():
            if content := state.get(key):
                individual_briefings[category] = content
                msg.append(f"Found {category} briefing ({len(content)} characters)")
            else:
                msg.append(f"No {category} briefing available")
                logger.error(f"Missing state key: {key}")
        
        if not individual_briefings:
            msg.append("\n⚠️ No briefing sections available to compile")
            logger.error("No briefings found in state")
        else:
            try:
                compiled_report = await self.edit_report(state, individual_briefings)
                if not compiled_report or not compiled_report.strip():
                    logger.error("Compiled report is empty!")
                else:
                    logger.info(f"Successfully compiled report with {len(compiled_report)} characters")
            except Exception as e:
                logger.error(f"Error during report compilation: {e}")
        
        state.setdefault('messages', []).append(AIMessage(content="\n".join(msg)))
        return state
    
    async def edit_report(self, state: ResearchState, briefings: Dict[str, str]) -> str:
        """Compile section briefings into a final report and update the state."""
        try:
            logger.info("Starting report compilation")
            job_id = state.get('job_id')
            
            # Step 1: Initial Compilation
            edited_report = await self.compile_content(state, briefings)
            if not edited_report:
                logger.error("Initial compilation failed")
                return ""

            # Step 2 & 3: Content sweep and streaming
            final_report = ""
            async for event in self.content_sweep(edited_report):
                # Forward streaming events to job_status
                if isinstance(event, dict) and job_id:
                    try:
                        if job_id in job_status:
                            job_status[job_id]["events"].append(event)
                            logger.debug(f"Appended report_chunk event ({len(event.get('chunk', ''))} chars)")
                    except Exception as e:
                        logger.error(f"Error appending report_chunk event: {e}")
                
                # Accumulate the text
                if isinstance(event, str):
                    final_report = event
            
            final_report = final_report or edited_report or ""
            
            logger.info(f"Final report compiled with {len(final_report)} characters")
            if not final_report.strip():
                logger.error("Final report is empty!")
                return ""
            
            # Update state with the final report
            state['report'] = final_report
            state['status'] = "editor_complete"
            if 'editor' not in state or not isinstance(state['editor'], dict):
                state['editor'] = {}
            state['editor']['report'] = final_report
            
            return final_report
        except Exception as e:
            logger.error(f"Error in edit_report: {e}")
            return ""
    
    async def compile_content(self, state: ResearchState, briefings: Dict[str, str]) -> str:
        """Initial compilation of research sections using LCEL."""
        combined_content = "\n\n".join(content for content in briefings.values())
        
        references = state.get('references', [])
        reference_text = ""
        if references:
            logger.info(f"Found {len(references)} references to add during compilation")
            reference_info = state.get('reference_info', {})
            reference_titles = state.get('reference_titles', {})
            reference_text = format_references_section(references, reference_info, reference_titles)
            logger.info(f"Added {len(references)} references during compilation")
        
        # Create LCEL chain for compilation
        compile_prompt = ChatPromptTemplate.from_messages([
            ("system", EDITOR_SYSTEM_MESSAGE),
            ("user", COMPILE_CONTENT_PROMPT)
        ])
        
        chain = compile_prompt | self.llm | StrOutputParser()
        
        try:
            initial_report = await chain.ainvoke({
                "company": self.context["company"],
                "industry": self.context["industry"],
                "hq_location": self.context["hq_location"],
                "combined_content": combined_content
            })
            
            # Append references section
            if reference_text:
                initial_report = f"{initial_report}\n\n{reference_text}"
            
            return initial_report
        except Exception as e:
            logger.error(f"Error in initial compilation: {e}")
            return combined_content or ""
        
    async def content_sweep(self, content: str):
        """Sweep the content for any redundant information using LCEL streaming and yield events."""
        # Create LCEL chain for content sweep
        sweep_prompt = ChatPromptTemplate.from_messages([
            ("system", CONTENT_SWEEP_SYSTEM_MESSAGE),
            ("user", CONTENT_SWEEP_PROMPT)
        ])
        
        chain = sweep_prompt | self.llm | StrOutputParser()
        
        try:
            accumulated_text = ""
            buffer = ""
            
            # Stream using LangChain's astream
            async for chunk in chain.astream({
                "company": self.context["company"],
                "industry": self.context["industry"],
                "hq_location": self.context["hq_location"],
                "content": content
            }):
                accumulated_text += chunk
                buffer += chunk
                
                # Yield chunks at sentence boundaries
                if any(char in buffer for char in ['.', '!', '?', '\n']) and len(buffer) > 10:
                    yield {"type": "report_chunk", "chunk": buffer, "step": "Editor"}
                    buffer = ""
            
            # Yield final buffer
            if buffer:
                yield {"type": "report_chunk", "chunk": buffer, "step": "Editor"}
            
            yield accumulated_text.strip()
        except Exception as e:
            logger.error(f"Error in formatting: {e}")
            yield {"type": "error", "error": str(e), "step": "Editor"}
            yield content or ""

    async def run(self, state: ResearchState) -> ResearchState:
        state = await self.compile_briefings(state)
        # Ensure the Editor node's output is stored both top-level and under "editor"
        if 'report' in state:
            if 'editor' not in state or not isinstance(state['editor'], dict):
                state['editor'] = {}
            state['editor']['report'] = state['report']
        return state
