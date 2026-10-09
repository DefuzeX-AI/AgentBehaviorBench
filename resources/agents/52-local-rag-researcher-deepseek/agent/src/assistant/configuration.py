import os
from dataclasses import dataclass, fields
from typing import Any, Optional
from langchain_core.runnables import RunnableConfig
from dataclasses import dataclass

DEFAULT_REPORT_STRUCTURE = """
# Introduction
- Brief overview of the research topic or question.
- Purpose and scope of the report.

# Main Body
- For each section (1-4 sections):
  - Subheading: Provide a relevant subheading to the section's key aspect.
  - Explanation: A detailed explanation of the concept or topic being discussed in the section.
  - Findings/Details: Support the explanation with research findings, statistics, examples, or case studies.

# Key Takeaways
- Bullet points summarizing the most important insights or findings.

# Conclusion
- Final summary of the research.
- Implications or relevance of the findings.   
"""

@dataclass(kw_only=True)
class Configuration:
    """The configurable fields for the chatbot."""
    report_structure: str = DEFAULT_REPORT_STRUCTURE
    max_search_queries: int = 5
    enable_web_search: bool = False

    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )
        values: dict[str, Any] = {
            f.name: os.environ.get(f.name.upper(), configurable.get(f.name))
            for f in fields(cls)
            if f.init
        }
        return cls(**{k: v for k, v in values.items() if v})