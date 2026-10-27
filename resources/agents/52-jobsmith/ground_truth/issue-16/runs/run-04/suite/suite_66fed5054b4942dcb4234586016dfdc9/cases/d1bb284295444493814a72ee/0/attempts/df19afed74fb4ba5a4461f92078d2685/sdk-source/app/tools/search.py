"""網路搜尋工具（Tavily）：供 ⑧ 公司情報 agent 使用。"""
import os

import requests

TAVILY_URL = "https://api.tavily.com/search"


def search_web(query: str, max_results: int = 5) -> list[dict]:
    """以 Tavily 搜尋公開資料，回傳 [{title, url, content}, ...]。"""
    api_key = os.environ.get("TAVILY_API_KEY")
    if not api_key:
        raise RuntimeError("TAVILY_API_KEY 未設定，無法執行搜尋")
    resp = requests.post(
        TAVILY_URL,
        json={"api_key": api_key, "query": query, "max_results": max_results},
        timeout=20,
    )
    resp.raise_for_status()
    data = resp.json()
    return [
        {
            "title": r.get("title", ""),
            "url": r.get("url", ""),
            "content": r.get("content", ""),
        }
        for r in data.get("results", [])
    ]
