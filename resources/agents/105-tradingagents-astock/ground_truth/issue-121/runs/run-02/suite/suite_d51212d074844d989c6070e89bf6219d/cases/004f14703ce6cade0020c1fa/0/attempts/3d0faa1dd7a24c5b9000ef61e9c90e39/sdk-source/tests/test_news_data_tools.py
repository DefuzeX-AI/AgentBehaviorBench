import pytest

from tradingagents.agents.utils import news_data_tools


@pytest.mark.unit
def test_get_news_rejects_non_code_ticker_without_vendor_call(monkeypatch):
    called = False

    def fake_route_to_vendor(*args, **kwargs):
        nonlocal called
        called = True
        return "unexpected"

    monkeypatch.setattr(news_data_tools, "route_to_vendor", fake_route_to_vendor)

    result = news_data_tools.get_news.invoke(
        {
            "ticker": "\u9492\u7535\u6c60",
            "start_date": "2026-07-01",
            "end_date": "2026-07-07",
        }
    )

    assert called is False
    assert "6-digit A-stock code" in result
    assert "search keywords" in result


@pytest.mark.unit
def test_get_news_routes_valid_six_digit_code(monkeypatch):
    def fake_route_to_vendor(method, ticker, start_date, end_date):
        assert method == "get_news"
        assert ticker == "000629"
        assert start_date == "2026-07-01"
        assert end_date == "2026-07-07"
        return "ok"

    monkeypatch.setattr(news_data_tools, "route_to_vendor", fake_route_to_vendor)

    assert (
        news_data_tools.get_news.invoke(
            {
                "ticker": "000629",
                "start_date": "2026-07-01",
                "end_date": "2026-07-07",
            }
        )
        == "ok"
    )


@pytest.mark.unit
def test_get_insider_transactions_rejects_non_code_ticker(monkeypatch):
    called = False

    def fake_route_to_vendor(*args, **kwargs):
        nonlocal called
        called = True
        return "unexpected"

    monkeypatch.setattr(news_data_tools, "route_to_vendor", fake_route_to_vendor)

    result = news_data_tools.get_insider_transactions.invoke(
        {"ticker": "\u9492\u7535\u6c60"}
    )

    assert called is False
    assert "6-digit A-stock code" in result
