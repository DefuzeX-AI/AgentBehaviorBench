from explainer.prompts import (
    DEVELOPER_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    EXPLAINER_SYSTEM_PROMPT,
    ANALOGY_CREATOR_SYSTEM_PROMPT,
    VULNERABILITY_EXPERT_SYSTEM_PROMPT,
)
from explainer.service.config import get_chat_model
from langgraph.prebuilt import create_react_agent
from langgraph_swarm import create_handoff_tool, create_swarm

model = get_chat_model()

transfer_to_developer = create_handoff_tool(
    agent_name="developer",
    description="Tool to hand control to the Developer for code examples and technical implementations.",
)
transfer_to_summarizer = create_handoff_tool(
    agent_name="summarizer",
    description="Tool to hand control to the Summarizer for concise summaries, key points, and TL;DR responses.",
)
transfer_to_explainer = create_handoff_tool(
    agent_name="explainer",
    description="Tool to hand control to the Explainer for detailed step-by-step breakdowns and educational explanations.",
)
transfer_to_analogy_creator = create_handoff_tool(
    agent_name="analogy_creator",
    description="Tool to hand control to the Analogy Creator for creating relatable analogies and metaphors for complex concepts.",
)
transfer_to_vulnerability_expert = create_handoff_tool(
    agent_name="vulnerability_expert",
    description="Tool to hand control to the Vulnerability Expert for analyzing potential weaknesses in arguments and methodology.",
)

developer = create_react_agent(
    model,
    prompt=DEVELOPER_SYSTEM_PROMPT,
    tools=[
        transfer_to_summarizer,
        transfer_to_explainer,
        transfer_to_analogy_creator,
        transfer_to_vulnerability_expert,
    ],
    name="developer",
)

summarizer = create_react_agent(
    model,
    prompt=SUMMARIZER_SYSTEM_PROMPT,
    tools=[
        transfer_to_developer,
        transfer_to_explainer,
        transfer_to_analogy_creator,
        transfer_to_vulnerability_expert,
    ],
    name="summarizer",
)

explainer = create_react_agent(
    model,
    prompt=EXPLAINER_SYSTEM_PROMPT,
    tools=[
        transfer_to_developer,
        transfer_to_summarizer,
        transfer_to_analogy_creator,
        transfer_to_vulnerability_expert,
    ],
    name="explainer",
)

analogy_creator = create_react_agent(
    model,
    prompt=ANALOGY_CREATOR_SYSTEM_PROMPT,
    tools=[
        transfer_to_developer,
        transfer_to_summarizer,
        transfer_to_explainer,
        transfer_to_vulnerability_expert,
    ],
    name="analogy_creator",
)

vulnerability_expert = create_react_agent(
    model,
    prompt=VULNERABILITY_EXPERT_SYSTEM_PROMPT,
    tools=[
        transfer_to_developer,
        transfer_to_summarizer,
        transfer_to_explainer,
        transfer_to_analogy_creator,
    ],
    name="vulnerability_expert",
)

# Swarm with default agent as explainer
agent_swarm = create_swarm(
    [
        developer,
        summarizer,
        explainer,
        analogy_creator,
        vulnerability_expert,
    ],
    default_active_agent="explainer",
)

app = agent_swarm.compile()
