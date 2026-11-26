"""Run the native SingleCommandInputRunner once per nonempty text input.

The runner owns its LangGraph workflow, prompts, tools and browser lifecycle.
Return GraphChatResult.summary (usually planner JSON), not aggregate JUnit counts.
RunnableConfig is accepted for the ABB interface; the native runner has no
RunnableConfig argument. Native setup and execution exceptions propagate.
"""
import asyncio
import uuid

class HerculesGraphBridge:
    def __init__(self):
        from testzeus_hercules.core.runner import SingleCommandInputRunner
        self._SingleCommandInputRunner = SingleCommandInputRunner
        self._closed = False

    def _validate(self, value):
        if not isinstance(value, str) or not value.strip():
            raise ValueError("Input must be a non-empty plain text test description or feature.")
        return value

    def invoke(self, value, config=None):
        """
        Synchronously invoke the Hercules agent for a single test input.
        Args:
            value (str): Test description, feature, or scenario.
            config: Optional ABB interface config; the native runner has no matching argument.
        Returns:
            str: Native GraphChatResult summary, normally planner JSON.
        """
        return asyncio.run(self.ainvoke(value, config=config))

    async def ainvoke(self, value, config=None):
        """
        Asynchronously invoke the Hercules agent for a single test input.
        Args:
            value (str): Test description, feature, or scenario.
            config: Optional ABB interface config; the native runner has no matching argument.
        Returns:
            str: Native GraphChatResult summary, normally planner JSON.
        """
        if self._closed:
            raise RuntimeError("HerculesGraphBridge is closed")
        text = self._validate(value)
        stake_id = f"bba_{uuid.uuid4().hex[:8]}"
        runner = self._SingleCommandInputRunner(
            stake_id=stake_id,
            command=text,
            dont_terminate_browser_after_run=False,
        )
        try:
            await runner.start()
            if runner.result and getattr(runner.result, "summary", None):
                return runner.result.summary
            elif runner.result:
                return getattr(runner.result, "__dict__", {}) or {"error": "No summary produced", "state": str(runner.result)}
            else:
                return {"error": "No result produced by runner."}
        finally:
            shutdown = getattr(runner, "shutdown", None)
            if callable(shutdown):
                try:
                    await shutdown()
                except Exception:
                    pass

    def close(self):
        """Mark the binding closed. Future invocations will fail."""
        self._closed = True

    async def aclose(self):
        """Async variant of close."""
        self.close()

def create_graph():
    """ABB/BBA-required factory. Returns a fresh HerculesGraphBridge instance."""
    return HerculesGraphBridge()
