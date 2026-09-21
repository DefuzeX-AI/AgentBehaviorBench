"""ABB message/result boundary for 51bitquant/ai-hedge-fund-crypto.

Upstream entrypoint: src.agent.Agent, built and invoked as main.py's live mode does with the shipped config.yaml (tickers, intervals, strategies, model) and a fresh portfolio. Agent.run() sends a fixed human message; the only free-text slot in the workflow input is that message, so the Case Input is placed there and the rest of run()'s state is kept. The graph PNG (rendered through the mermaid.ink API) is not drawn. The answer is the portfolio manager's final message.
"""
import asyncio
import shutil
from collections.abc import Mapping
from datetime import datetime
from pathlib import Path

REPO = Path("/opt/agent/agent")


class AgentGraph:
    def __init__(self):
        if not Path("config.yaml").exists():
            shutil.copy(REPO / "config.yaml", "config.yaml")
        from src.agent import Agent
        from src.utils import settings

        self._settings = settings
        self._agent = Agent(intervals=settings.signals.intervals, strategies=settings.signals.strategies,
                            show_agent_graph=False)

    def invoke(self, value, config=None, **kwargs):
        return asyncio.run(self.ainvoke(value, config, **kwargs))

    async def ainvoke(self, value, config=None, **kwargs):
        from langchain_core.messages import HumanMessage

        text = value.get("message") if isinstance(value, Mapping) else value
        if not isinstance(text, str) or not text.strip():
            raise ValueError("Supply the Case Input as message text")
        settings = self._settings
        tickers = settings.signals.tickers
        portfolio = {
            "cash": settings.initial_cash,
            "margin_requirement": settings.margin_requirement,
            "margin_used": 0.0,
            "positions": {ticker: {"long": 0.0, "short": 0.0, "long_cost_basis": 0.0, "short_cost_basis": 0.0,
                                   "short_margin_used": 0.0} for ticker in tickers},
            "realized_gains": {ticker: {"long": 0.0, "short": 0.0} for ticker in tickers},
        }
        state = {
            "messages": [HumanMessage(content=text)],
            "data": {"primary_interval": settings.primary_interval, "intervals": self._agent.intervals,
                     "tickers": tickers, "portfolio": portfolio, "end_date": datetime.now(), "analyst_signals": {}},
            "metadata": {"show_reasoning": settings.show_reasoning, "model_name": settings.model.name,
                         "model_provider": settings.model.provider, "model_base_url": settings.model.base_url},
        }
        final_state = await asyncio.to_thread(self._agent.agent.invoke, state)
        answer = final_state["messages"][-1].content
        if not isinstance(answer, str) or not answer.strip():
            raise RuntimeError("Agent returned no answer text")
        return {"answer": answer}

    def close(self):
        self._agent = None


def create_graph():
    return AgentGraph()
