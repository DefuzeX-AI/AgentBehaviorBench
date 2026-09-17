from typing import Dict, Any
import json
import pandas as pd
from langchain_core.messages import HumanMessage
from src.graph import AgentState, BaseNode, show_agent_reasoning
from indicators import (calculate_trend_signals,
                        calculate_mean_reversion_signals,
                        calculate_momentum_signals,
                        calculate_volatility_signals,
                        calculate_stat_arb_signals,
                        weighted_signal_combination,
                        normalize_pandas)


class MacdStrategy(BaseNode):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Sophisticated technical analysis system that combines multiple trading strategies for multiple tickers:
        1. Trend Following
        2. Mean Reversion
        3. Momentum
        4. Volatility Analysis
        5. Statistical Arbitrage Signals
        """

        data = state['data']
        data['name'] = "MacdStrategy"

        data = state.get("data", {})
        tickers = data.get("tickers", [])
        intervals = data.get("intervals", [])

        # Initialize analysis for each ticker
        technical_analysis = {}
        for ticker in tickers:
            technical_analysis[ticker] = {}

        # Combine all signals using a weighted ensemble approach
        strategy_weights = {
            "trend": 0.25,
            "mean_reversion": 0.20,
            "momentum": 0.25,
            "volatility": 0.15,
            "stat_arb": 0.15,
        }

        for ticker in tickers:
            for interval in intervals:
                df = data.get(f"{ticker}_{interval.value}", pd.DataFrame())

                trend_signals = calculate_trend_signals(df)
                mean_reversion_signals = calculate_mean_reversion_signals(df)
                momentum_signals = calculate_momentum_signals(df)

                volatility_signals = calculate_volatility_signals(df)
                stat_arb_signals = calculate_stat_arb_signals(df)

                combined_signal = weighted_signal_combination(
                    {
                        "trend": trend_signals,
                        "mean_reversion": mean_reversion_signals,
                        "momentum": momentum_signals,
                        "volatility": volatility_signals,
                        "stat_arb": stat_arb_signals,
                    },
                    strategy_weights,
                )

                # Generate detailed analysis report for this ticker
                technical_analysis[ticker][interval.value] = {
                    "signal": combined_signal["signal"],
                    "confidence": round(combined_signal["confidence"] * 100),
                    "strategy_signals": {
                        "trend_following": {
                            "signal": trend_signals["signal"],
                            "confidence": round(trend_signals["confidence"] * 100),
                            "metrics": normalize_pandas(trend_signals["metrics"]),
                        },
                        "mean_reversion": {
                            "signal": mean_reversion_signals["signal"],
                            "confidence": round(mean_reversion_signals["confidence"] * 100),
                            "metrics": normalize_pandas(mean_reversion_signals["metrics"]),
                        },
                        "momentum": {
                            "signal": momentum_signals["signal"],
                            "confidence": round(momentum_signals["confidence"] * 100),
                            "metrics": normalize_pandas(momentum_signals["metrics"]),
                        },
                        "volatility": {
                            "signal": volatility_signals["signal"],
                            "confidence": round(volatility_signals["confidence"] * 100),
                            "metrics": normalize_pandas(volatility_signals["metrics"]),
                        },
                        "statistical_arbitrage": {
                            "signal": stat_arb_signals["signal"],
                            "confidence": round(stat_arb_signals["confidence"] * 100),
                            "metrics": normalize_pandas(stat_arb_signals["metrics"]),
                        },
                    },
                }

        # Create the technical analyst message
        message = HumanMessage(
            content=json.dumps(technical_analysis),
            name="technical_analyst_agent",
        )

        if state["metadata"]["show_reasoning"]:
            show_agent_reasoning(technical_analysis, "Technical Analyst")

        # Add the signal to the analyst_signals list
        state["data"]["analyst_signals"]["technical_analyst_agent"] = technical_analysis

        # return state
        # # print(state)

        return {
            "messages": [message],
            "data": data,
        }
