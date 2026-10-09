import datetime
from typing_extensions import Literal
from langgraph.constants import Send
from langgraph.graph import START, END, StateGraph
from langchain_core.runnables.config import RunnableConfig
from src.assistant.configuration import Configuration
from src.assistant.vector_db import get_or_create_vector_db
from src.assistant.state import ResearcherState, ResearcherStateInput, ResearcherStateOutput, QuerySearchState, QuerySearchStateInput, QuerySearchStateOutput
from src.assistant.prompts import RESEARCH_QUERY_WRITER_PROMPT, RELEVANCE_EVALUATOR_PROMPT, SUMMARIZER_PROMPT, REPORT_WRITER_PROMPT
from src.assistant.utils import format_documents_with_metadata, invoke_llm, invoke_ollama, parse_output, tavily_search, Evaluation, Queries

# Number of query to process in parallel for each batch
# Change depending on the performance of the system
BATCH_SIZE = 3

def generate_research_queries(state: ResearcherState, config: RunnableConfig):
    print("--- Generating research queries ---")
    user_instructions = state["user_instructions"]
    max_queries = config["configurable"].get("max_search_queries", 3)
    
    query_writer_prompt = RESEARCH_QUERY_WRITER_PROMPT.format(
        max_queries=max_queries,
        date=datetime.datetime.now().strftime("%Y/%m/%d %H:%M")
    )
    
    # Using local Deepseek R1 model with Ollama
    result = invoke_ollama(
        model='deepseek-r1:7b',
        system_prompt=query_writer_prompt,
        user_prompt=f"Generate research queries for this user instruction: {user_instructions}",
        output_format=Queries
    )
    
    # Using external LLM providers with OpenRouter: GPT-4o, Claude, Deepseek R1,... 
    # result = invoke_llm(
    #     model='gpt-4o-mini',
    #     system_prompt=query_writer_prompt,
    #     user_prompt=f"Generate research queries for this user instruction: {user_instructions}",
    #     output_format=Queries
    # )

    return {"research_queries": result.queries}

def search_queries(state: ResearcherState):
    # Kick off the search for each query by calling initiate_query_research
    print("--- Searching queries ---")
    pass

def initiate_query_research(state: ResearcherState):
    # Kick off the search for each query in parallel using Send method and calling the "search_and_summarize_query" subgraph
    return [
        Send("search_and_summarize_query", {"query": s})
        for s in state["research_queries"]
    ]

def search_queries(state: ResearcherState):
    # Kick off the search for each query by calling initiate_query_research
    print("--- Searching queries ---")
    # Get the current processing position from state or initialize to 0
    current_position = state.get("current_position", 0)

    return {"current_position": current_position + BATCH_SIZE}


def check_more_queries(state: ResearcherState) -> Literal["search_queries", "generate_final_answer"]:
    """Check if there are more queries to process"""
    current_position = state.get("current_position", 0)
    if current_position < len(state["research_queries"]):
        return "search_queries"
    return "generate_final_answer"

def initiate_query_research(state: ResearcherState):
    # Get the next batch of queries
    queries = state["research_queries"]
    current_position = state["current_position"]
    batch_end = min(current_position, len(queries))
    current_batch = queries[current_position - BATCH_SIZE:batch_end]

    # Return the batch of queries to process
    return [
        Send("search_and_summarize_query", {"query": s})
        for s in current_batch
    ]

def retrieve_rag_documents(state: QuerySearchState):
    """Retrieve documents from the RAG database."""
    print("--- Retrieving documents ---")
    query = state["query"]
    vectorstore = get_or_create_vector_db()
    vectorstore_retreiver = vectorstore.as_retriever(search_type="similarity", search_kwargs={"k": 3})
    documents = vectorstore_retreiver.invoke(query)

    return {"retrieved_documents": documents}

def evaluate_retrieved_documents(state: QuerySearchState):
    query = state["query"]
    retrieved_documents = state["retrieved_documents"]
    evaluation_prompt = RELEVANCE_EVALUATOR_PROMPT.format(
        query=query,
        documents=format_documents_with_metadata(retrieved_documents)
    )
    
    # Using local Deepseek R1 model with Ollama
    evaluation = invoke_ollama(
        model='deepseek-r1:7b',
        system_prompt=evaluation_prompt,
        user_prompt=f"Evaluate the relevance of the retrieved documents for this query: {query}",
        output_format=Evaluation
    )
    
    # Using external LLM providers with OpenRouter: GPT-4o, Claude, Deepseek R1,... 
    # evaluation = invoke_llm(
    #     model='gpt-4o-mini',
    #     system_prompt=evaluation_prompt,
    #     user_prompt=f"Evaluate the relevance of the retrieved documents for this query: {query}",
    #     output_format=Evaluation
    # )

    return {"are_documents_relevant": evaluation.is_relevant}

def route_research(state: QuerySearchState, config: RunnableConfig) -> Literal["summarize_query_research", "web_research", "__end__"]:
    """ Route the research based on the documents relevance """

    if state["are_documents_relevant"]:
        return "summarize_query_research"
    elif config["configurable"].get("enable_web_search", False):
        return "web_research"
    else:
        print("Skipping query due to irrelevant documents and web search disabled.")
        return "__end__"

def web_research(state: QuerySearchState):
    print("--- Web research ---")
    output = tavily_search(state["query"])
    search_results = output["results"]

    return {"web_search_results": search_results}

def summarize_query_research(state: QuerySearchState):
    query = state["query"]

    information = None
    if state["are_documents_relevant"]:
        # If documents are relevant: Use RAG documents
        information = state["retrieved_documents"]
    else:
        # If documents are irrelevant: Use web search results,
        # if enabled, otherwise query will be skipped in the previous router node
        information = state["web_search_results"]

    summary_prompt = SUMMARIZER_PROMPT.format(
        query=query,
        docmuents=information
    )
    
    # Using local Deepseek R1 model with Ollama
    summary = invoke_ollama(
        model='deepseek-r1:7b',
        system_prompt=summary_prompt,
        user_prompt=f"Generate a research summary for this query: {query}"
    )
    # Remove thinking part (reasoning between <think> tags)
    summary = parse_output(summary)["response"]
    
    # Using external LLM providers with OpenRouter: GPT-4o, Claude, Deepseek R1,... 
    # summary = invoke_llm(
    #     model='gpt-4o-mini',
    #     system_prompt=summary_prompt,
    #     user_prompt=f"Generate a research summary for this query: {query}"
    # )

    return {"search_summaries": [summary]}

def generate_final_answer(state: ResearcherState, config: RunnableConfig):
    print("--- Generating final answer ---")
    report_structure = config["configurable"].get("report_structure", "")
    answer_prompt = REPORT_WRITER_PROMPT.format(
        instruction=state["user_instructions"],
        report_structure=report_structure,
        information="\n\n---\n\n".join(state["search_summaries"])
    )

    # Using local Deepseek R1 model with Ollama
    result = invoke_ollama(
        model='deepseek-r1:7b',
        system_prompt=answer_prompt,
        user_prompt=f"Generate a research summary using the provided information."
    )
    # Remove thinking part (reasoning between <think> tags)
    answer = parse_output(result)["response"]
    
    # # Using external LLM providers with OpenRouter: GPT-4o, Claude, Deepseek R1,... 
    # answer = invoke_llm(
    #     model='gpt-4o-mini',
    #     system_prompt=answer_prompt,
    #     user_prompt=f"Generate a research summary using the provided information."
    # )
    
    return {"final_answer": answer}

# Create subghraph for searching each query
query_search_subgraph = StateGraph(QuerySearchState, input=QuerySearchStateInput, output=QuerySearchStateOutput)

# Define subgraph nodes for searching the query
query_search_subgraph.add_node(retrieve_rag_documents)
query_search_subgraph.add_node(evaluate_retrieved_documents)
query_search_subgraph.add_node(web_research)
query_search_subgraph.add_node(summarize_query_research)

# Set entry point and define transitions for the subgraph
query_search_subgraph.add_edge(START, "retrieve_rag_documents")
query_search_subgraph.add_edge("retrieve_rag_documents", "evaluate_retrieved_documents")
query_search_subgraph.add_conditional_edges("evaluate_retrieved_documents", route_research)
query_search_subgraph.add_edge("web_research", "summarize_query_research")
query_search_subgraph.add_edge("summarize_query_research", END)

# Create main research agent graph
researcher_graph = StateGraph(ResearcherState, input=ResearcherStateInput, output=ResearcherStateOutput, config_schema=Configuration)

# Define main researcher nodes
researcher_graph.add_node(generate_research_queries)
researcher_graph.add_node(search_queries)
researcher_graph.add_node("search_and_summarize_query", query_search_subgraph.compile())
researcher_graph.add_node(generate_final_answer)

# Define transitions for the main graph
researcher_graph.add_edge(START, "generate_research_queries")
researcher_graph.add_edge("generate_research_queries", "search_queries")
researcher_graph.add_conditional_edges("search_queries", initiate_query_research, ["search_and_summarize_query"])
researcher_graph.add_conditional_edges("search_and_summarize_query", check_more_queries)
researcher_graph.add_edge("generate_final_answer", END)

# Compile the researcher graph
researcher = researcher_graph.compile()