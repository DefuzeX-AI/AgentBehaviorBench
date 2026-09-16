---
agent_description: |
  The Agentic Company Researcher is an agentic AI workflow built using LangGraph technology that orchestrates multiple specialized research nodes to gather, curate, and synthesize comprehensive company information. It accepts a textual company name as primary input, with optional parameters including company URL, industry, headquarters location, and a job identifier. The agent proceeds asynchronously through a stateful multi-node pipeline involving data grounding, specialized financial, industry, company, and news analysis via Tavily API, content collection, curation using relevance scores, briefing creation with Google Gemini 2.5 Flash, and final report editing using GPT-5.1. The output is a streaming sequence of state updates culminating in a deep, structured markdown company research report.

input_type: text

strategy_group:
  schema_version: kuma.strategy_group_selection.v1
  id: CAND-009
  version: "1"

---

## Production Use Scenario

This agent is intended for production environments requiring automated, high-quality, multi-source company research reports. Users provide the company name optionally supplemented with its URL, industry classification, and headquarters location. The agent performs asynchronous research using interconnected nodes that scrape company websites, conduct targeted web searches for financial, industry, company, and news data, curate and enrich content based on relevance scoring, and generate category-specific briefings. It finally compiles these briefings into a comprehensive, professionally formatted markdown report. The system integrates with external APIs (Tavily, Gemini, OpenAI) and supports streaming progressive output, suitable for REST API backends serving frontend clients or other consumers. It handles failures gracefully and provides progress and diagnostic events.

## Behaviors to Test

- Accept textual input representing the company name and map correctly to the research workflow.
- Properly handle optional company metadata such as URL, industry, and headquarters location.
- Execute the asynchronous workflow nodes in the specified order:
  - Grounding (website crawl)
  - Financial Analysis
  - News Scanning
  - Industry Analysis
  - Company Analysis
  - Collection and Curation of data with relevance filtering
  - Briefing generation per category using Gemini LLM
  - Enrichment with raw content
  - Final report compilation and editing using GPT LLM
- Stream incremental state updates including research progress events.
- Produce a final complete report in clean markdown format integrating all curated sources.
- Correctly emit events related to research initiation, crawl successes/errors, query generation, search completion, briefing starts/completions, enrichment, and editing.
- Support invocation through the LangGraph in_process adapter with explicit input_key "company" for text input.
- Operate with required environment variables (TAVILY_API_KEY, OPENAI_API_KEY, GEMINI_API_KEY) supplied via environment with LLM interception.
- Use Python 3.11 environment and dependencies as specified.

## Known Limitations or Prohibited Behaviors

- The agent requires external API keys for Tavily, OpenAI, and Gemini; it does not manage these keys internally.
- It does not accept structured JSON inputs; only plain text input mapped as the company name is supported.
- The agent assumes a stable network connection for asynchronous external API calls; network failures may cause partial failures.
- The streaming output is asynchronous and requires client compatibility to consume incremental states.
- The internal graph accepts optional inputs but the LangGraph adapter restricts input to text on "company" alone.
- The system does not support persistent memory beyond transient job states and optional MongoDB logging; historical continuity is out of scope.
- No direct support for multi-turn conversations or incremental question answering.
- The final report generation depends on the quality and availability of online data; no fabricated or speculative content is generated.
- Usage of GPT-5.1 and Gemini models requires proper access and may incur costs.
- The agent does not perform active web crawling beyond initial grounding or searches through Tavily SDK constrained by API limits.
- Does not support input customization beyond predefined parameters.

