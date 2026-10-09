from src.assistant.graph import researcher
from src.assistant.vector_db import get_or_create_vector_db
from dotenv import load_dotenv

load_dotenv()

report_structure = """
1. Introduction
- Brief overview of the research topic or question.
- Purpose and scope of the report.

2. Main Body
- For each section (e.g., Section 1, Section 2, Section 3, etc.):
  - Provide a subheading related to the key aspect of the research.
  - Include explanation, findings, and supporting details.

3. Key Takeaways
- Bullet points summarizing the most important insights or findings.

4. Conclusion
- Final summary of the research.
- Implications or relevance of the findings.
"""

# Define the initial state
initial_state = {
    "user_instructions": "Can you help me understand the current state of AI reasoning models, particularly DeepSeek R-1? I keep hearing about breakthroughs in mathematical reasoning and problem-solving capabilities, but I want to know how these models are actually being implemented and used in real applications. I am Really interested in learning about its performance compared to other LLMs, what makes its training approach unique, and if there are any concerns about reliability or limitations. Looking for recent benchmarks and real-world applications, not just theoretical capabilities.",
}

# Langgraph researcher config
config = {
  "configurable": {
    "enable_web_search": False,
    "report_structure": report_structure,
    "max_search_queries": 5
}}

# Init vector store
# Must add your own documents in the /files directory before running this script
vector_db = get_or_create_vector_db()

# Run the researcher graph
for output in researcher.stream(initial_state, config=config):
    for key, value in output.items():
        print(f"Finished running: **{key}**")
        print(value)

