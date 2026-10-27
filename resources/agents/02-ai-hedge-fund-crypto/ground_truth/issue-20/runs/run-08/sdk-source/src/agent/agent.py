from typing import List, Dict, Optional
from langchain_core.messages import HumanMessage
from datetime import datetime
from utils import Interval, save_graph_as_png, parse_str_to_json
from .workflow import Workflow


class Agent:

    def __init__(self, intervals: List[Interval], strategies: List[str], show_agent_graph: bool = True):
        workflow = Workflow.create_workflow(intervals=intervals, strategies=strategies)
        self.intervals = intervals
        self.strategies = strategies
        self.agent = workflow.compile()
        if show_agent_graph:
            file_path = ""
            for strategy_name in strategies:
                file_path += strategy_name + "_"
                file_path += "graph.png"
            save_graph_as_png(self.agent, file_path)

    def run(
            self,
            primary_interval: Interval,
            tickers: List[str],
            end_date: datetime,
            portfolio: Dict,
            show_reasoning: bool = False,
            model_name: str = "gpt-4o",
            model_provider: str = "openai",
            model_base_url: Optional[str] = None
    ):
        """
        Executes the trading workflow using the specified configuration.
        Parameters:
            primary_interval (Interval): The primary time interval used for decision making.
            tickers (List[str]): List of asset symbols to include in the backtest or live run.
            end_date (str): The end date for historical data used in the workflow.
            portfolio (Dict): The initial state of the portfolio, including cash, positions, and margins.
            show_reasoning (bool, optional): If True, includes model reasoning in the output. Defaults to False.
            model_name (str, optional): The name of the LLM model to use. Defaults to "gpt-4o".
            model_provider (str, optional): The provider of the LLM model. Defaults to "openai".
            model_base_url (str, optional): The base URL of the LLM model. Defaults to None.

        Returns:
        None
        """

        final_state = self.agent.invoke(
            {
                "messages": [
                    HumanMessage(
                        content="Make trading decisions based on the provided data.",
                    )
                ],
                "data": {
                    "primary_interval": primary_interval,
                    "intervals": self.intervals,
                    "tickers": tickers,
                    "portfolio": portfolio,
                    "end_date": end_date,
                    "analyst_signals": {},
                },
                "metadata": {
                    "show_reasoning": show_reasoning,
                    "model_name": model_name,
                    "model_provider": model_provider,
                    "model_base_url": model_base_url,
                },
            },
        )
        # print("the final state:", final_state["data"]["analyst_signals"])
        return {
            "decisions": parse_str_to_json(final_state["messages"][-1].content),
            "analyst_signals": final_state["data"]["analyst_signals"],
        }
