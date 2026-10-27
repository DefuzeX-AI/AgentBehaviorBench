import pytest

from app.tools import search as search_mod


class _FakeResp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        pass

    def json(self):
        return self._payload


def test_search_web_parses_results(monkeypatch):
    payload = {"results": [
        {"title": "未來智能 評價", "url": "https://x.com/a", "content": "福利不錯"},
        {"title": "薪資", "url": "https://x.com/b", "content": "月薪 6 萬起"},
    ]}
    monkeypatch.setenv("TAVILY_API_KEY", "tvly-test")
    monkeypatch.setattr(search_mod.requests, "post", lambda *a, **k: _FakeResp(payload))

    results = search_mod.search_web("未來智能")

    assert len(results) == 2
    assert results[0]["title"] == "未來智能 評價"
    assert results[0]["url"] == "https://x.com/a"
    assert "福利" in results[0]["content"]


def test_search_web_raises_without_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    with pytest.raises(RuntimeError):
        search_mod.search_web("未來智能")
