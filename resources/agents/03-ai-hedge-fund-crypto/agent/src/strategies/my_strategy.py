from typing import Dict, Any
import json
import pandas as pd
from langchain_core.messages import HumanMessage
from src.graph import AgentState, BaseNode


class MyStrategy(BaseNode):
    def __call__(self, state: AgentState) -> Dict[str, Any]:
        """
        Custom strategy implementation that processes market data across multiple timeframes.
        """
        # Access the state data
        data = state.get("data", {})
        data['name'] = "MyStrategy"  # Set strategy name for visualization

        # Get tickers and intervals from the state
        tickers = data.get("tickers", [])
        intervals = data.get("intervals", [])

        # Initialize analysis dictionary to store results
        technical_analysis = {}
        for ticker in tickers:
            technical_analysis[ticker] = {}

        # Process each ticker and interval combination
        for ticker in tickers:
            for interval in intervals:
                # Access the price data for this ticker and interval
                df = data.get(f"{ticker}_{interval.value}", pd.DataFrame())

                if df.empty:
                    continue

                # Implement your custom technical analysis here
                # Example: Simple moving average crossover strategy
                df['sma_fast'] = df['close'].rolling(window=10).mean()
                df['sma_slow'] = df['close'].rolling(window=30).mean()

                # Generate signal based on your strategy logic
                signal = "neutral"
                confidence = 50

                if df['sma_fast'].iloc[-1] > df['sma_slow'].iloc[-1]:
                    signal = "bullish"
                    confidence = 70
                elif df['sma_fast'].iloc[-1] < df['sma_slow'].iloc[-1]:
                    signal = "bearish"
                    confidence = 70

                # Store analysis results
                technical_analysis[ticker][interval.value] = {
                    "signal": signal,
                    "confidence": confidence,
                    "strategy_signals": {
                        "simple_ma_crossover": {
                            "signal": signal,
                            "confidence": confidence,
                            "metrics": {
                                "sma_fast": float(df['sma_fast'].iloc[-1]),
                                "sma_slow": float(df['sma_slow'].iloc[-1]),
                                "price": float(df['close'].iloc[-1])
                            }
                        }
                    }
                }

        # Create message with analysis results
        message = HumanMessage(
            content=json.dumps(technical_analysis),
            name="my_strategy_agent",
        )

        # Update the state with the analysis
        state["data"]["analyst_signals"]["my_strategy_agent"] = technical_analysis

        # Return the updated state
        return {
            "messages": [message],
            "data": data,
        }