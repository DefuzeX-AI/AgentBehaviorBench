import json
from typing import Dict, Any, Optional
from langchain_core.messages import HumanMessage
from .state import AgentState, show_agent_reasoning
from .base_node import BaseNode
from utils import Interval


class RiskManagementNode(BaseNode):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """Controls position sizing based on real-world risk factors for multiple tickers."""
        data = state.get('data', {})
        data['name'] = "RiskManagementNode"

        portfolio = data.get("portfolio", {})
        tickers = data.get("tickers", [])
        primary_interval: Optional[Interval] = data.get("primary_interval")

        risk_analysis = {}
        current_prices = {}  # Store prices here to avoid redundant API calls

        for ticker in tickers:

            price_df = data.get(f"{ticker}_{primary_interval.value}")

            # Calculate portfolio value
            current_price = price_df["close"].iloc[-1]
            current_prices[ticker] = current_price  # Store the current price

            # Calculate current position value for this ticker
            current_position_value = portfolio.get("cost_basis", {}).get(ticker, 0.0)

            # Calculate total portfolio value using stored prices
            total_portfolio_value = portfolio.get("cash", 0.0) + sum(
                portfolio.get("cost_basis", {}).get(t, 0.0) for t in portfolio.get("cost_basis", {}))

            # Base limit is 20% of portfolio for any single position
            position_limit = total_portfolio_value * 0.20

            # For existing positions, subtract current position value from limit
            remaining_position_limit = position_limit - current_position_value

            # Ensure we don't exceed available cash
            max_position_size = min(remaining_position_limit, portfolio.get("cash", 0.0))

            risk_analysis[ticker] = {
                "remaining_position_limit": float(max_position_size),
                "current_price": float(current_price),
                "reasoning": {
                    "portfolio_value": float(total_portfolio_value),
                    "current_position": float(current_position_value),
                    "position_limit": float(position_limit),
                    "remaining_limit": float(remaining_position_limit),
                    "available_cash": float(portfolio.get("cash", 0.0)),
                },
            }

        message = HumanMessage(
            content=json.dumps(risk_analysis),
            name="risk_management_agent",
        )

        if state["metadata"]["show_reasoning"]:
            show_agent_reasoning(risk_analysis, "Risk Management Agent")

        # Add the signal to the analyst_signals list
        data["analyst_signals"]["risk_management_agent"] = risk_analysis

        return {
            "messages": [message],
            "data": data,
        }

        # return state
