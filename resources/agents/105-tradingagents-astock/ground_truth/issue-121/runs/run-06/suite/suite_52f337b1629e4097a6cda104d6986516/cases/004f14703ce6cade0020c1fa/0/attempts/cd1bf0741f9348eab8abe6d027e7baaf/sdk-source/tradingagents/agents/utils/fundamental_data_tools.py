from langchain_core.tools import tool
from typing import Annotated
from tradingagents.dataflows.interface import route_to_vendor

# 三张财报表按分析日只返回已公布的报表；空日期会让数据层整段不筛，拿到之后才公布的报表
_MISSING_DATE = (
    "Error: {name} requires curr_date (yyyy-mm-dd, the current analysis date). "
    "Call it again with curr_date set."
)


@tool
def get_fundamentals(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd"],
) -> str:
    """
    Retrieve comprehensive fundamental data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd
    Returns:
        str: A formatted report containing comprehensive fundamental data
    """
    return route_to_vendor("get_fundamentals", ticker, curr_date)


@tool
def get_balance_sheet(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd (required)"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
) -> str:
    """
    Retrieve balance sheet data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd. Only reports
            already published by this date are returned.
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
    Returns:
        str: A formatted report containing balance sheet data
    """
    if not (curr_date or "").strip():
        return _MISSING_DATE.format(name="get_balance_sheet")
    return route_to_vendor("get_balance_sheet", ticker, freq, curr_date)


@tool
def get_cashflow(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd (required)"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
) -> str:
    """
    Retrieve cash flow statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd. Only reports
            already published by this date are returned.
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
    Returns:
        str: A formatted report containing cash flow statement data
    """
    if not (curr_date or "").strip():
        return _MISSING_DATE.format(name="get_cashflow")
    return route_to_vendor("get_cashflow", ticker, freq, curr_date)


@tool
def get_income_statement(
    ticker: Annotated[str, "6-digit A-stock code (e.g. 600379). Must be numeric, NOT company name"],
    curr_date: Annotated[str, "current date you are trading at, yyyy-mm-dd (required)"],
    freq: Annotated[str, "reporting frequency: annual/quarterly"] = "quarterly",
) -> str:
    """
    Retrieve income statement data for a given ticker symbol.
    Uses the configured fundamental_data vendor.
    Args:
        ticker (str): Ticker symbol of the company
        curr_date (str): Current date you are trading at, yyyy-mm-dd. Only reports
            already published by this date are returned.
        freq (str): Reporting frequency: annual/quarterly (default quarterly)
    Returns:
        str: A formatted report containing income statement data
    """
    if not (curr_date or "").strip():
        return _MISSING_DATE.format(name="get_income_statement")
    return route_to_vendor("get_income_statement", ticker, freq, curr_date)