"""Alpha Vantage 出站请求的超时回归（v0.5.20）。

`requests.get` 不给 timeout 的语义是**永远等下去**：网关挂起时整轮分析进程
活着、零输出、永不返回，和 #100 的 LLM 挂死是同一类静默失败。

三件事一起钉：请求真的带上了超时、超时值确实是个正数（写成 0/None 等于白加）、
以及加超时没有改掉正常返回和限流识别这两条既有行为。

全程不碰真实 Alpha Vantage：`requests.get` 被替身顶掉，API key 用假值。
"""

import json

import pytest

from tradingagents.dataflows import alpha_vantage_common as av


class _FakeResponse:
    def __init__(self, text: str):
        self.text = text

    def raise_for_status(self):
        return None


@pytest.fixture
def fake_api_key(monkeypatch):
    """`_make_api_request` 会先读环境变量，没有就直接 ValueError。"""
    monkeypatch.setenv("ALPHA_VANTAGE_API_KEY", "test-key-never-sent")


def _capture_request(monkeypatch, text: str = "timestamp,close\n2026-09-21,10"):
    """换掉 `requests.get`，记录它收到的参数并返回固定响应。"""
    calls = {}

    def fake_get(url, **kwargs):
        calls["url"] = url
        calls["kwargs"] = kwargs
        return _FakeResponse(text)

    monkeypatch.setattr(av.requests, "get", fake_get)
    return calls


@pytest.mark.unit
def test_request_carries_the_module_timeout(monkeypatch, fake_api_key):
    calls = _capture_request(monkeypatch)
    av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})

    assert "timeout" in calls["kwargs"], (
        "requests.get 没带 timeout —— 语义是永远等下去，挂起的网关会让整轮分析静默卡死"
    )
    assert calls["kwargs"]["timeout"] == av.REQUEST_TIMEOUT


@pytest.mark.unit
def test_timeout_policy_is_a_positive_number():
    # 阴性对照：把常量写成 0 / None / 负数，"有超时"就退化回"没超时"
    # （requests 收到 None 就是无限等），而上面那条断言照样绿。
    assert isinstance(av.REQUEST_TIMEOUT, (int, float))
    assert not isinstance(av.REQUEST_TIMEOUT, bool)
    assert av.REQUEST_TIMEOUT > 0


@pytest.mark.unit
def test_normal_csv_response_still_returned(monkeypatch, fake_api_key):
    # 正常行为不能被超时改动动到：CSV 原样返回。
    body = "timestamp,close\n2026-09-21,10"
    _capture_request(monkeypatch, text=body)
    assert av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"}) == body


@pytest.mark.unit
def test_rate_limit_still_detected(monkeypatch, fake_api_key):
    # 限流识别走的是响应体 JSON 里的 "Information"，与超时无关，必须照旧生效。
    _capture_request(
        monkeypatch,
        text=json.dumps({"Information": "Our standard API rate limit is 25 requests per day"}),
    )
    with pytest.raises(av.AlphaVantageRateLimitError):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})


@pytest.mark.unit
def test_missing_api_key_still_raises_before_any_request(monkeypatch):
    # 上游给少了（没配 key）：应当在发请求之前就报错，而不是带着空 key 发出去。
    calls = _capture_request(monkeypatch)
    monkeypatch.delenv("ALPHA_VANTAGE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="ALPHA_VANTAGE_API_KEY"):
        av._make_api_request("TIME_SERIES_DAILY", {"symbol": "AAPL"})
    assert calls == {}, "缺 key 时不该发出任何请求"
