from langchain_core.tools import tool
from typing import Annotated
import re
from tradingagents.dataflows.interface import route_to_vendor

_A_STOCK_CODE_RE = re.compile(r"^\d{6}$")


def _invalid_a_stock_code_message(tool_name: str, ticker: str) -> str:
    return (
        f"Invalid ticker for `{tool_name}`: {ticker!r}. "
        "This tool only accepts a 6-digit A-stock code, not Chinese text, "
        "company names, sector names, concepts, or search keywords. "
        "Use the original analysis ticker/code in the tool call."
    )


def _validate_a_stock_code(tool_name: str, ticker: str) -> tuple[bool, str]:
    code = str(ticker or "").strip()
    if not _A_STOCK_CODE_RE.fullmatch(code):
        return False, _invalid_a_stock_code_message(tool_name, code)
    return True, code


@tool
def get_news(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name or Chinese text"],
    start_date: Annotated[str, "Start date in yyyy-mm-dd format"],
    end_date: Annotated[str, "End date in yyyy-mm-dd format"],
) -> str:
    """
    Retrieve news data for a given stock code.
    Uses the configured news_data vendor.
    Args:
        ticker (str): 6-digit A-stock code, e.g. 600379, 300750. Must be the numeric code, not the company name.
        start_date (str): Start date in yyyy-mm-dd format
        end_date (str): End date in yyyy-mm-dd format
    Returns:
        str: A formatted string containing news data
    """
    ok, code_or_message = _validate_a_stock_code("get_news", ticker)
    if not ok:
        return code_or_message
    return route_to_vendor("get_news", code_or_message, start_date, end_date)

@tool
def get_global_news(
    curr_date: Annotated[str, "Current date in yyyy-mm-dd format"],
    look_back_days: Annotated[int, "Number of days to look back"] = 7,
    limit: Annotated[int, "Maximum number of articles to return"] = 5,
) -> str:
    """
    Retrieve global news data.
    Uses the configured news_data vendor.
    Args:
        curr_date (str): Current date in yyyy-mm-dd format
        look_back_days (int): Number of days to look back (default 7)
        limit (int): Maximum number of articles to return (default 5)
    Returns:
        str: A formatted string containing global news data
    """
    return route_to_vendor("get_global_news", curr_date, look_back_days, limit)

@tool
def get_insider_transactions(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name"],
) -> str:
    """
    Retrieve insider transaction information about a company.
    Uses the configured news_data vendor.
    Args:
        ticker (str): 6-digit A-stock code, e.g. 600379
    Returns:
        str: A report of insider transaction data
    """
    ok, code_or_message = _validate_a_stock_code("get_insider_transactions", ticker)
    if not ok:
        return code_or_message
    return route_to_vendor("get_insider_transactions", code_or_message)
