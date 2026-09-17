import pytest

from react_agent import graph


@pytest.mark.asyncio
@pytest.mark.langsmith
async def test_react_agent_simple_passthrough() -> None:
    # Add your own tests here.
    await graph.ainvoke(
        {"messages": [("user", "Hi there!")]},
    )
