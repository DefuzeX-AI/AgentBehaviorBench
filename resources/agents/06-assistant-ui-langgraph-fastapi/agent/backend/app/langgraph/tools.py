from langchain_core.tools import tool
from datetime import datetime, timezone


@tool(return_direct=True)
def get_stock_price(stock_symbol: str):
    """Call to get the current stock price and related information for a given stock symbol."""
    # This is a mock implementation
    mock_stock_data = {
        "AAPL": {
            "symbol": "AAPL",
            "company_name": "Apple Inc.",
            "current_price": 173.50,
            "change": 2.35,
            "change_percent": 1.37,
            "volume": 52436789,
            "market_cap": "2.73T",
            "pe_ratio": 28.5,
            "fifty_two_week_high": 198.23,
            "fifty_two_week_low": 124.17,
            "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        },
        # Add more mock data for other symbols as needed
    }

    return mock_stock_data["AAPL"]


tools = [get_stock_price]
