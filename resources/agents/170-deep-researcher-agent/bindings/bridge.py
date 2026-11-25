"""Invoke the native NAT-owned LangGraph through its public WorkflowRunner."""
import asyncio
import os
import uuid


class DeepResearcherBridge:
    def __init__(self):
        self._closed = False

    def invoke(self, value, config=None):
        return asyncio.run(self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        if self._closed:
            raise RuntimeError("DeepResearcherBridge is closed")
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Expected a nonempty text query")
        from deep_researcher_mcp.workflow_runner import WorkflowRunner
        runner = WorkflowRunner(os.environ["DEEP_RESEARCHER_MCP_CONFIG"])
        try:
            await runner.start()
            # The native runner owns graph configuration and checkpoint identity.
            # Do not preclassify, change depth, bypass tools or alter native prompts.
            outcome = await runner.run_query(value, conversation_id=str(uuid.uuid4()))
            if outcome.status != "success":
                raise RuntimeError(outcome.error)
            return outcome.model_dump(mode="json")
        finally:
            await runner.stop()

    def close(self):
        self._closed = True

    async def aclose(self):
        self.close()


def create_graph():
    return DeepResearcherBridge()
