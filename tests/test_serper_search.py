from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.agent_tools import search_market_news


class _FakeResponse:
    status_code = 200
    text = "ok"

    def json(self) -> dict:
        return {
            "news": [
                {
                    "title": "A股融资买入额上升，市场风险偏好改善",
                    "link": "https://example.com/a-share-margin",
                    "date": "2026-05-11",
                    "source": "Example News",
                    "snippet": "融资买入额上升可能反映杠杆资金活跃度提高。",
                }
            ]
        }


def test_search_market_news_uses_serper_news_endpoint() -> None:
    captured = {}

    def _fake_post(url, headers=None, json=None, timeout=None):  # type: ignore[no-untyped-def]
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return _FakeResponse()

    with patch("src.agent_tools.get_env") as get_env, patch("src.agent_tools.requests.post", side_effect=_fake_post):
        get_env.side_effect = lambda name, default="": {
            "SERPER_API_KEY": "serper-key",
            "SERPER_SEARCH_ENDPOINT": "https://google.serper.dev/news",
            "SERPER_HTTP_TIMEOUT_SEC": "9",
        }.get(name, default)

        result = search_market_news("A股 融资买入额 上行 原因", recency_days=7)

    assert captured["url"] == "https://google.serper.dev/news"
    assert captured["headers"]["X-API-KEY"] == "serper-key"
    assert captured["json"]["q"] == "A股 融资买入额 上行 原因"
    assert captured["json"]["num"] == 5
    assert result["status"] == "ok"
    assert result["references"][0]["source_title"] == "A股融资买入额上升，市场风险偏好改善"
    assert result["references"][0]["source_url"] == "https://example.com/a-share-margin"
