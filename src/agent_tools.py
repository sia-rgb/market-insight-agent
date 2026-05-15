from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import requests

from .agent_runtime import get_env, get_timeout_seconds


MARKET_NEWS_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "search_market_news",
        "description": (
            "搜索指定资产、指标或资产类别在特定时间窗口内的相关新闻报道、分析师分析、"
            "市场评论、政策/资金面/行业相关因素。搜索目标是补充背景信息，不要求证明直接因果。"
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "检索词，例如：'沪深300 资金流向 市场情绪 分析师 解读'",
                },
                "recency_days": {
                    "type": "integer",
                    "description": "回溯天数，例如7表示最近7天",
                    "minimum": 1,
                    "maximum": 30,
                },
            },
            "required": ["query", "recency_days"],
        },
    },
}


def _truncate_text(text: str, max_len: int) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_len:
        return raw
    return f"{raw[: max_len - 3]}..."


def search_market_news(query: str, recency_days: int) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    q = str(query).strip()
    days = max(1, min(int(recency_days), 30))
    if not q:
        return {
            "status": "error",
            "error_type": "invalid_request",
            "error_message": "检索词为空，无法获取外部信息",
            "references": [],
            "compact_context": "",
        }

    serper_key = get_env("SERPER_API_KEY")
    if not serper_key:
        return {
            "status": "error",
            "error_type": "missing_api_key",
            "error_message": "未配置搜索引擎 API Key，无法获取外部信息",
            "references": [],
            "compact_context": "",
        }

    endpoint = get_env("SERPER_SEARCH_ENDPOINT", "https://google.serper.dev/news")
    timeout_sec = get_timeout_seconds("SERPER_HTTP_TIMEOUT_SEC", 30.0)
    payload = {
        "q": q,
        "num": 5,
        "tbs": f"qdr:d{days}",
    }
    headers = {"Content-Type": "application/json", "X-API-KEY": serper_key}
    try:
        resp = requests.post(endpoint, headers=headers, json=payload, timeout=timeout_sec)
        if resp.status_code >= 400:
            detail = _truncate_text(resp.text, 280)
            return {
                "status": "error",
                "error_type": "http_error",
                "error_message": f"搜索引擎请求失败: HTTP {resp.status_code}",
                "references": [],
                "compact_context": "",
                "error_detail": detail,
            }

        body = resp.json()
        results = body.get("news") or body.get("organic") or []
        refs: list[dict[str, Any]] = []
        compact_parts: list[str] = []
        max_compact_len = 1600
        for item in results:
            if not isinstance(item, dict):
                continue
            title = _truncate_text(str(item.get("title", "")).strip(), 120)
            url = _truncate_text(str(item.get("link", "") or item.get("url", "")).strip(), 220)
            content = _truncate_text(str(item.get("snippet", "") or item.get("content", "")).strip(), 260)
            if not (title or url or content):
                continue
            refs.append(
                {
                    "source_url": url,
                    "source_title": title or "Serper Search Result",
                    "publish_date": str(item.get("date", "") or item.get("published_date", "")).strip(),
                    "retrieved_at": now,
                    "relevance_note": content,
                }
            )
            compact_parts.append(f"{title} | {url} | {content}")
            if len(" || ".join(compact_parts)) >= max_compact_len:
                break

        compact_context = _truncate_text(" || ".join(compact_parts), max_compact_len)
        if not refs:
            return {
                "status": "ok",
                "error_type": "",
                "error_message": "",
                "references": [],
                "compact_context": "未检索到有效新闻结果",
            }
        return {
            "status": "ok",
            "error_type": "",
            "error_message": "",
            "references": refs,
            "compact_context": compact_context,
        }
    except requests.Timeout:
        return {
            "status": "error",
            "error_type": "timeout",
            "error_message": "搜索引擎请求超时",
            "references": [],
            "compact_context": "",
        }
    except requests.RequestException as ex:
        return {
            "status": "error",
            "error_type": "network_error",
            "error_message": "搜索引擎网络错误",
            "references": [],
            "compact_context": "",
            "error_detail": _truncate_text(str(ex), 220),
        }
    except Exception as ex:
        return {
            "status": "error",
            "error_type": type(ex).__name__,
            "error_message": "搜索引擎调用异常",
            "references": [],
            "compact_context": "",
            "error_detail": _truncate_text(str(ex), 220),
        }
