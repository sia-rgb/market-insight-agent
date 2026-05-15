from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.dashboard_agent_insights import build_dashboard_agent_insights


def _dashboard_payload() -> dict:
    return {
        "latest_date": "2026-05-12",
        "effective_close_date": "2026-05-11",
        "rankings": {
            "top_abs_change": [
                {
                    "date": "2026-05-11",
                    "source_sheet": "权益-两融余额",
                    "asset_class": "equity",
                    "asset_name": "A股两融",
                    "asset_key": "margin_balance",
                    "series_key": "margin_balance::financing_buy",
                    "ticker": "",
                    "metric_name": "融资买入额",
                    "value": 373618766049.0,
                    "unit": "raw",
                    "previous_value": 306379336038.0,
                    "daily_abs_change": 67239430011.0,
                    "daily_pct_change": 21.95,
                    "direction": "up",
                },
                {
                    "date": "2026-05-11",
                    "source_sheet": "权益-两融余额",
                    "asset_class": "equity",
                    "asset_name": "",
                    "metric_name": "无效样本",
                    "daily_abs_change": 1.0,
                    "daily_pct_change": 1.0,
                    "direction": "up",
                },
            ]
        },
    }


def _series_payload() -> dict:
    def series(source_sheet, asset_class, asset_name, metric_name, pct):
        return {
            "source_sheet": source_sheet,
            "asset_class": asset_class,
            "asset_name": asset_name,
            "asset_key": asset_name,
            "series_key": f"{source_sheet}::{asset_name}::{metric_name}",
            "ticker": None,
            "metric_name": metric_name,
            "unit": "raw",
            "observations": [
                {
                    "date": "2026-04-30",
                    "value": 100.0 + pct,
                    "previous_value": 100.0,
                    "daily_abs_change": pct,
                    "daily_pct_change": pct,
                    "direction": "up" if pct > 0 else "down",
                }
            ],
        }

    return {
        "latest_date": "2026-05-12",
        "effective_close_date": "2026-05-11",
        "rankings": {
            "top_abs_change": [
                {
                    "date": "2026-05-11",
                    "source_sheet": "权益-两融余额",
                    "asset_class": "equity",
                    "asset_name": "A股两融",
                    "metric_name": "融资买入额",
                    "daily_pct_change": 21.95,
                    "daily_abs_change": 10.0,
                    "direction": "up",
                }
            ]
        },
        "series_all": [
            series("权益-全球股指", "equity", "纳斯达克指数", "最新收盘价", 99.0),
            series("权益-散户情绪资金流向", "equity", "沪深300", "largeBillInflowMoney", -450.0),
            series("衍生品-50ETF期权", "derivative", "上证50ETF华夏", "daily_call_volume", 36.0),
            series("权益-两融余额", "equity", "A股两融", "融资卖出额", -22.5),
            series("权益-A股交易量", "equity", "A股市场", "上证指数", 13.3),
            series("权益-VIX", "equity", "VIX.GI", "close", -10.2),
            series("固收-同业拆借利率", "fixed_income", "SHIBORON.IR", "close", 6.8),
        ],
    }


def test_build_dashboard_agent_insights_outputs_daily_demo_payload() -> None:
    with patch("src.agent_llm.get_env", return_value=""):
        payload = build_dashboard_agent_insights(
            dashboard_payload=_dashboard_payload(),
            top_n=5,
            enable_external_search=False,
        )

    assert payload["status"] == "ok"
    assert payload["as_of_date"] == "2026-05-11"
    assert len(payload["insights"]) == 1
    insight = payload["insights"][0]
    assert insight["asset_name"] == "A股两融"
    assert insight["metric_name"] == "融资买入额"
    assert insight["search_queries"][0]["generated_by"] == "deterministic_template"
    assert "日度" in insight["possible_drivers"]
    assert insight["confidence"] == "low"
    assert insight["note"] == "外部信息仅作为可能线索，不构成直接因果证明"


def test_build_dashboard_agent_insights_can_target_historical_date_from_series_all() -> None:
    with patch("src.agent_llm.get_env", return_value=""):
        payload = build_dashboard_agent_insights(
            dashboard_payload=_series_payload(),
            top_n=5,
            enable_external_search=False,
            target_date="2026-04-30",
        )

    assert payload["status"] == "ok"
    assert payload["as_of_date"] == "2026-04-30"
    assert len(payload["insights"]) == 5
    assert {item["source_sheet"] for item in payload["insights"]} == {
        "权益-散户情绪资金流向",
        "衍生品-50ETF期权",
        "权益-两融余额",
        "权益-A股交易量",
        "权益-VIX",
    }
    assert all(item["date"] == "2026-04-30" for item in payload["insights"])


def test_dashboard_agent_search_query_uses_readable_metric_aliases() -> None:
    with patch("src.agent_llm.get_env", return_value=""):
        payload = build_dashboard_agent_insights(
            dashboard_payload=_series_payload(),
            top_n=1,
            enable_external_search=False,
            target_date="2026-04-30",
        )

    query = payload["insights"][0]["search_queries"][0]["generated_query"]
    assert "largeBillInflowMoney" not in query
    assert "None" not in query
    assert "大单资金" in query


def test_dashboard_agent_uses_serper_seed_refs_without_second_llm_tool_call() -> None:
    calls = {}

    def _fake_llm(context, allow_external_search=True):  # type: ignore[no-untyped-def]
        calls["allow_external_search"] = allow_external_search
        calls["seed_count"] = len(context.get("external_evidence_seed", []))
        return {
            "driver_analysis": "内部数据已显示该指标日度触发异动，Serper 线索显示两融资金活跃度同步升温。",
            "driver_note": "mock_llm",
            "external_references": context.get("external_evidence_seed", []),
            "driver_evidence": [
                {
                    "evidence_grade": "confirmed",
                    "published_at": "2026-05-11",
                    "source": "example.com",
                    "title": "两融余额上升",
                    "summary": "两融资金活跃。",
                }
            ],
            "query_log": [],
        }

    with patch("src.dashboard_agent_insights.search_market_news") as search, patch(
        "src.dashboard_agent_insights._generate_insight_with_llm",
        side_effect=_fake_llm,
    ):
        search.return_value = {
            "status": "ok",
            "references": [
                {
                    "source_title": "两融余额上升",
                    "source_url": "https://example.com/margin",
                    "publish_date": "2026-05-11",
                    "retrieved_at": "2026-05-12T00:00:00Z",
                    "relevance_note": "两融资金活跃。",
                }
            ],
        }
        payload = build_dashboard_agent_insights(
            dashboard_payload=_dashboard_payload(),
            top_n=1,
            enable_external_search=True,
        )

    assert calls["seed_count"] == 1
    assert calls["allow_external_search"] is False
    assert payload["insights"][0]["external_context_used"] is True


def test_target_date_search_expands_recency_window_for_historical_demo() -> None:
    with patch("src.dashboard_agent_insights.search_market_news") as search, patch(
        "src.dashboard_agent_insights._generate_insight_with_llm",
        return_value={"driver_analysis": "日度解释", "driver_note": "mock", "external_references": [], "driver_evidence": []},
    ):
        search.return_value = {"status": "ok", "references": []}
        build_dashboard_agent_insights(
            dashboard_payload=_series_payload(),
            top_n=1,
            enable_external_search=True,
            target_date="2026-04-30",
        )

    assert search.call_args.kwargs["recency_days"] > 7
