import asyncio
from datetime import date
from typing import TypedDict

from langchain_core.messages import HumanMessage
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.memory import MemorySaver
from pybox import AsyncLocalPyBoxManager
from tablegpt import DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR
from tablegpt.agent import create_tablegpt_graph
from tablegpt.agent.file_reading import Stage


class Attachment(TypedDict):
    """Contains at least one dictionary with the key filename."""

    filename: str
    """The dataset uploaded in this session can be a filename, file path, or object storage address."""


# tablegpt-agent fully supports async invocation
async def main() -> None:
    llm = ChatOpenAI(
        openai_api_base="YOUR_VLLM_URL",
        openai_api_key="whatever",
        model_name="TableGPT2-7B",
    )

    # Use local pybox manager for development and testing
    pybox_manager = AsyncLocalPyBoxManager(profile_dir=DEFAULT_TABLEGPT_IPYKERNEL_PROFILE_DIR)

    agent = create_tablegpt_graph(
        llm=llm,
        pybox_manager=pybox_manager,
        # We use MemorySaver as a checkpointer to record memory automatically.
        # See <https://langchain-ai.github.io/langgraph/concepts/persistence>
        checkpointer=MemorySaver(),
        # All code generated in this run will be executed in the kernel with kernel_id 'some-session-id'.
        session_id="some-session-id",
    )

    attachment_msg = HumanMessage(
        content="",
        # The dataset can be viewed in examples/datasets/titanic.csv.
        additional_kwargs={"attachments": [Attachment(filename="examples/datasets/titanic.csv")]},
    )
    await agent.ainvoke(
        input={
            "entry_message": attachment_msg,
            "processing_stage": Stage.UPLOADED,
            "messages": [attachment_msg],
            "parent_id": "some-parent-id1",
            "date": date.today(),  # noqa: DTZ011
        },
        config={
            "configurable": {"thread_id": "some-thread-id"},
        },
    )

    human_message = HumanMessage(content="How many men survived?")

    async for event in agent.astream_events(
        input={
            # After using checkpoint, you only need to add new messages here.
            "messages": [human_message],
            "parent_id": "some-parent-id2",
            "date": date.today(),  # noqa: DTZ011
        },
        version="v2",
        # We configure the same thread_id to use checkpoints to retrieve the memory of the last run.
        config={"configurable": {"thread_id": "some-thread-id"}},
    ):
        print(event)  # noqa: T201


asyncio.run(main())
