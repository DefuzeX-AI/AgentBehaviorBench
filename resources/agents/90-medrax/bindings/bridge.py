"""
LangGraph binding for MedRAX: Medical Reasoning Agent for Chest X-ray.

This binding translates one text (or {"message": text}) Case input into the native MedRAX LangGraph agent's input state. It validates input, relays config, and provides resource cleanup. The agent natively owns its tool/model lifecycles. See README.md and medrax/agent/agent.py for public API and execution details.

Example input:
    {'message': 'What findings do you observe in this chest X-ray?'}
Returns:
    Full LangGraph state (including messages, tool calls/results, etc.) as returned by the native Agent.
"""
import asyncio
from collections.abc import Mapping
from pathlib import Path


def state_from_input(value):
    """
    Accept text or exactly {'message': text}; reject unrepresented attachments or extra fields.
    """
    if isinstance(value, Mapping):
        if set(value) != {'message'}:
            raise ValueError('MedRAX requires exactly one "message" field (text only)')
        value = value['message']
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Supply a non-empty message (finding/question) for MedRAX')
    # MedRAX expects messages as list of dicts: [{role, content}]
    return {'messages': [{'role': 'user', 'content': value}]}


class AgentGraph:
    """
    Wrapper for the MedRAX native agent LangGraph workflow.

    Methods:
        invoke(value, config=None): Synchronously run one Case input through MedRAX.
        ainvoke(value, config=None): Asynchronously run one input.
        close(): Release underlying resources/agent.
    """
    def __init__(self):
        from medrax.agent.agent import Agent
        from medrax.utils.utils import load_prompts_from_file
        from medrax.tools import (
            ChestXRayClassifierTool, ChestXRaySegmentationTool,
            XRayVQATool, ChestXRayReportGeneratorTool,
            ImageVisualizerTool, DicomProcessorTool
        )
        from langgraph.checkpoint.memory import MemorySaver
        from langchain_openai import ChatOpenAI
        import os

        # Use defaults matching main.py for robust benchmarking.
        model_name = os.environ.get("OPENAI_MODEL", "gpt-4o")
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        openai_base_url = os.environ.get("OPENAI_BASE_URL")
        openai_kwargs = {}
        if openai_api_key:
            openai_kwargs["api_key"] = openai_api_key
        if openai_base_url:
            openai_kwargs["base_url"] = openai_base_url

        prompt_file = Path(__file__).resolve().parents[1] / "agent/medrax/docs/system_prompts.txt"
        prompts = load_prompts_from_file(str(prompt_file))
        system_prompt = prompts["MEDICAL_ASSISTANT"]

        # Match the six enabled tools in upstream main.py's selected_tools.
        tools = [
            ImageVisualizerTool(),
            DicomProcessorTool(temp_dir="/workspace/temp"),
            ChestXRayClassifierTool(device="cuda"),
            ChestXRaySegmentationTool(device="cuda", temp_dir=Path("/workspace/temp")),
            ChestXRayReportGeneratorTool(cache_dir="/model-weights", device="cuda"),
            XRayVQATool(cache_dir="/model-weights", device="cuda"),
        ]
        model = ChatOpenAI(model=model_name, temperature=0.7, top_p=0.95, **openai_kwargs)
        checkpointer = MemorySaver()
        self._agent = Agent(
            model,
            tools=tools,
            log_tools=True,
            log_dir="/workspace/logs",
            system_prompt=system_prompt,
            checkpointer=checkpointer,
        )
        self._workflow = self._agent.workflow
        self._closed = False

    def invoke(self, value, config=None):
        """
        Synchronously process one input via MedRAX LangGraph agent.

        Args:
            value: text or {'message': text}
            config: LangChain RunnableConfig for observation/callbacks (optional)
        Returns:
            Native LangGraph state as returned by the agent.
        Raises:
            ValueError, RuntimeError for invalid input or if closed; underlying agent exceptions otherwise.
        """
        if self._closed:
            raise RuntimeError("MedRAX binding is closed")
        state = state_from_input(value)
        return self._workflow.invoke(state, config=config)

    async def ainvoke(self, value, config=None):
        """
        Asynchronously process one input via MedRAX agent.

        Args:
            value: text or {'message': text}
            config: LangChain RunnableConfig (optional)
        Returns:
            Native LangGraph state.
        Raises:
            As above.
        """
        if self._closed:
            raise RuntimeError("MedRAX binding is closed")
        state = state_from_input(value)
        return await self._workflow.ainvoke(state, config=config)

    def close(self):
        """Release resources (underlying agent and tools). Repeatable and idempotent."""
        self._closed = True
        self._workflow = None
        agent = getattr(self, '_agent', None)
        if agent is not None:
            close = getattr(agent, 'close', None)
            if callable(close):
                try:
                    close()
                except Exception:
                    pass
            self._agent = None


def create_graph():
    """
    Factory for the MedRAX LangGraph binding.

    Returns:
        An object supporting invoke(value, config=None) and ainvoke(value, config=None),
        accepting text or {'message': text}. See module docstring for details.
    """
    return AgentGraph()
