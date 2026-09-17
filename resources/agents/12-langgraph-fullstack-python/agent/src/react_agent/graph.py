"""A simple chatbot."""

from langgraph.prebuilt import create_react_agent

graph = create_react_agent(
    "anthropic:claude-3-5-haiku-latest",
    tools=[],
    prompt="You are a friendly, curious, geeky AI.",
)
