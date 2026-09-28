import asyncio
from datetime import date

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from pybox import AsyncLocalPyBoxManager
from tablegpt.agent import create_tablegpt_graph


# tablegpt-agent fully supports async invocation
async def main() -> None:
    llm = ChatOpenAI(openai_api_base="YOUR_VLLM_URL", openai_api_key="whatever", model_name="TableGPT2-7B")

    # Use local pybox manager for development and testing
    pybox_manager = AsyncLocalPyBoxManager()

    agent = create_tablegpt_graph(
        llm=llm,
        pybox_manager=pybox_manager,
    )

    message = HumanMessage(content="Hi")
    _input = {
        "messages": [message],
        "parent_id": "some-parent-id",
        "date": date.today(),  # noqa: DTZ011
    }

    async for event in agent.astream_events(
        input=_input,
        version="v2",
    ):
        print(event)  # noqa: T201


asyncio.run(main())
