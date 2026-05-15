from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .agent_evidence import evidence_confidence, normalize_refs, render_evidence_driver_text
from .agent_llm import _generate_insight_with_llm
from .agent_tools import search_market_news
from .utils_common import _row_join_key


def _to_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _direction_text(direction: str) -> str:
    if direction == "up":
        return "上行"
    if direction == "down":
        return "下行"
    return "波动"


def _search_metric_text(metric_name: Any) -> str:
    text = _to_text(metric_name)
    aliases = {
        "largeBillInflowMoney": "大单资金净流入",
        "middleBillInflowMoney": "中单资金净流入",
        "smallBillInflowMoney": "小单资金净流入",
        "daily_call_volume": "认购期权成交量",
        "daily_put_volume": "认沽期权成交量",
        "daily_volume": "期权成交量",
        "daily_contract_rate": "期权合约换手率",
        "daily_call_position": "认购期权持仓量",
        "daily_put_position": "认沽期权持仓量",
        "daily_position": "期权持仓量",
        "close": "收盘价",
        "EDBclose": "收盘价",
    }
    return aliases.get(text, text)


def _search_asset_text(record: dict[str, Any]) -> str:
    asset_name = _to_text(record.get("asset_name", ""))
    ticker = _to_text(record.get("ticker", ""))
    if "|" in asset_name:
        return " ".join(part.strip() for part in asset_name.split("|") if part.strip())
    if ticker and ticker not in asset_name:
        return f"{ticker} {asset_name}".strip()
    return asset_name


def _is_valid_record(record: dict[str, Any]) -> bool:
    if not str(record.get("asset_name", "")).strip():
        return False
    if not str(record.get("metric_name", "")).strip():
        return False
    pct = _to_float(record.get("daily_pct_change"))
    abs_change = _to_float(record.get("daily_abs_change"))
    return pct is not None or abs_change is not None


def _build_search_query(record: dict[str, Any]) -> str:
    asset_name = _search_asset_text(record)
    metric_name = _search_metric_text(record.get("metric_name", ""))
    date = str(record.get("date", "")).strip()
    direction = _direction_text(str(record.get("direction", "")).strip())
    return f"{asset_name} {metric_name} {direction} {date} 市场原因 新闻 分析"


def _search_recency_days(record_date: str) -> int:
    try:
        target = datetime.fromisoformat(record_date).date()
    except ValueError:
        return 7
    today = datetime.now(timezone.utc).date()
    delta_days = (today - target).days
    if delta_days <= 7:
        return 7
    return max(7, min(delta_days + 3, 30))


def _build_daily_context(record: dict[str, Any], seed_refs: list[dict[str, Any]]) -> dict[str, Any]:
    date = str(record.get("date", "")).strip()
    return {
        "task": "generate_dashboard_daily_insight",
        "language": "zh-CN",
        "required_analysis_points": [
            "变化方向",
            "变化幅度",
            "数据驱动力分析",
        ],
        "time_window": {
            "date": date,
            "as_of_date": date,
            "frequency": "daily",
            "period_label": "日度",
        },
        "asset_fact": {
            "asset_name": str(record.get("asset_name", "")).strip(),
            "asset_class": str(record.get("asset_class", "")).strip(),
            "asset_key": str(record.get("asset_key", "")).strip(),
            "series_key": str(record.get("series_key", "")).strip(),
            "metric_name": str(record.get("metric_name", "")).strip(),
            "unit": str(record.get("unit", "")).strip(),
            "current_value": _to_float(record.get("value")),
            "previous_value": _to_float(record.get("previous_value")),
            "pct_change_pct": _to_float(record.get("daily_pct_change")),
            "abs_change": _to_float(record.get("daily_abs_change")),
            "monitor_change_field": "daily_pct_change",
            "monitor_change_value": _to_float(record.get("daily_pct_change")),
            "direction": str(record.get("direction", "")).strip(),
            "source_sheet": str(record.get("source_sheet", "")).strip(),
            "join_key": _row_join_key(record),
        },
        "historical_position": {
            "available": False,
            "note": "daily_dashboard_mvp",
        },
        "external_evidence_seed": normalize_refs(seed_refs),
        "external_search_policy": {
            "purpose": "supplemental_market_context",
            "not_required": "direct_causal_proof",
            "preferred_sources": [
                "相关新闻报道",
                "分析师分析",
                "市场评论",
                "政策/资金面/行业相关因素",
            ],
        },
        "tool_hints": {
            "max_search_rounds": 2,
            "search_recency_days": 7,
        },
    }


def _select_records(dashboard_payload: dict[str, Any], top_n: int) -> list[dict[str, Any]]:
    rankings = dashboard_payload.get("rankings") or {}
    records = rankings.get("top_abs_change") or []
    if not isinstance(records, list):
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in records:
        if not isinstance(item, dict) or not _is_valid_record(item):
            continue
        key = _row_join_key(item)
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
        if len(out) >= top_n:
            break
    return out


def _records_for_target_date(dashboard_payload: dict[str, Any], target_date: str) -> list[dict[str, Any]]:
    series_items = dashboard_payload.get("series_all") or dashboard_payload.get("series") or []
    if not isinstance(series_items, list):
        return []
    out: list[dict[str, Any]] = []
    for series in series_items:
        if not isinstance(series, dict):
            continue
        if str(series.get("source_sheet", "")).strip() == "权益-全球股指":
            continue
        observations = series.get("observations") or []
        if not isinstance(observations, list):
            continue
        for obs in observations:
            if not isinstance(obs, dict) or str(obs.get("date", "")).strip() != target_date:
                continue
            record = {
                "date": target_date,
                "source_sheet": _to_text(series.get("source_sheet", "")),
                "asset_class": _to_text(series.get("asset_class", "")),
                "asset_name": _to_text(series.get("asset_name", "")),
                "asset_key": _to_text(series.get("asset_key", "")),
                "series_key": _to_text(series.get("series_key", "")),
                "ticker": _to_text(series.get("ticker", "")),
                "metric_name": _to_text(series.get("metric_name", "")),
                "value": obs.get("value"),
                "unit": _to_text(series.get("unit", "")),
                "previous_value": obs.get("previous_value"),
                "daily_abs_change": obs.get("daily_abs_change"),
                "daily_pct_change": obs.get("daily_pct_change"),
                "direction": _to_text(obs.get("direction", "")),
            }
            if _is_valid_record(record):
                out.append(record)
    return out


def _select_records_for_target_date(
    dashboard_payload: dict[str, Any],
    target_date: str,
    top_n: int,
) -> list[dict[str, Any]]:
    records = _records_for_target_date(dashboard_payload, target_date=target_date)
    ranked = sorted(
        records,
        key=lambda item: abs(_to_float(item.get("daily_pct_change")) or 0.0),
        reverse=True,
    )
    picked: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    used_sheets: set[str] = set()
    for record in ranked:
        key = _row_join_key(record)
        sheet = str(record.get("source_sheet", "")).strip()
        if key in seen_keys or sheet in used_sheets:
            continue
        picked.append(record)
        seen_keys.add(key)
        used_sheets.add(sheet)
        if len(picked) >= top_n:
            return picked
    for record in ranked:
        key = _row_join_key(record)
        if key in seen_keys:
            continue
        picked.append(record)
        seen_keys.add(key)
        if len(picked) >= top_n:
            break
    return picked


def build_dashboard_agent_insights(
    dashboard_payload: dict[str, Any],
    top_n: int = 5,
    enable_external_search: bool = True,
    target_date: str | None = None,
) -> dict[str, Any]:
    requested_date = str(target_date or "").strip()
    records = (
        _select_records_for_target_date(dashboard_payload, target_date=requested_date, top_n=top_n)
        if requested_date
        else _select_records(dashboard_payload, top_n=top_n)
    )
    as_of_date = requested_date or str(dashboard_payload.get("effective_close_date") or dashboard_payload.get("latest_date") or "").strip()
    insights: list[dict[str, Any]] = []

    for record in records:
        query = _build_search_query(record)
        query_log: list[dict[str, Any]] = [
            {
                "generated_query": query,
                "generated_by": "deterministic_template",
                "generation_reason": "daily_dashboard_mover",
                "query_time": datetime.now(timezone.utc).isoformat(),
            }
        ]
        seed_refs: list[dict[str, Any]] = []
        if enable_external_search:
            recency_days = _search_recency_days(str(record.get("date", "")).strip())
            search_result = search_market_news(query=query, recency_days=recency_days)
            seed_refs = normalize_refs(search_result.get("references", []) or [])
            query_log[0]["search_status"] = search_result.get("status", "error")
            query_log[0]["error_type"] = search_result.get("error_type", "")
            query_log[0]["recency_days"] = recency_days

        context = _build_daily_context(record, seed_refs=seed_refs)
        generated = _generate_insight_with_llm(
            context=context,
            allow_external_search=False,
        )
        refs = normalize_refs(seed_refs + (generated.get("external_references", []) or []))
        driver_evidence = generated.get("driver_evidence", []) or []
        query_log.extend(generated.get("query_log", []) or [])
        possible_drivers = str(generated.get("driver_analysis", "")).strip()
        if not possible_drivers:
            possible_drivers = "内部数据已显示该指标日度触发异动；后续重点观察政策、资金面、市场评论与同类资产表现是否同步变化。"

        insights.append(
            {
                "record_id": _row_join_key(record),
                "date": str(record.get("date", "")).strip(),
                "source_sheet": str(record.get("source_sheet", "")).strip(),
                "asset_class": str(record.get("asset_class", "")).strip(),
                "asset_name": str(record.get("asset_name", "")).strip(),
                "metric_name": str(record.get("metric_name", "")).strip(),
                "direction": str(record.get("direction", "")).strip(),
                "value": _to_float(record.get("value")),
                "unit": str(record.get("unit", "")).strip(),
                "previous_value": _to_float(record.get("previous_value")),
                "daily_abs_change": _to_float(record.get("daily_abs_change")),
                "daily_pct_change": _to_float(record.get("daily_pct_change")),
                "search_queries": query_log,
                "external_references": refs,
                "external_context_used": bool(refs),
                "possible_drivers": possible_drivers,
                "evidence_summary": render_evidence_driver_text(driver_evidence),
                "confidence": evidence_confidence(driver_evidence),
                "agent_note": str(generated.get("driver_note", "")).strip(),
                "note": "外部信息仅作为可能线索，不构成直接因果证明",
            }
        )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "as_of_date": as_of_date,
        "status": "ok" if insights else "insufficient_data",
        "source": "dashboard_data",
        "insights": insights,
    }


def build_dashboard_agent_insights_from_file(
    dashboard_data_path: str,
    out_path: str,
    top_n: int = 5,
    enable_external_search: bool = True,
    target_date: str | None = None,
) -> dict[str, Any]:
    import json

    with open(dashboard_data_path, "r", encoding="utf-8") as f:
        dashboard_payload = json.load(f)
    payload = build_dashboard_agent_insights(
        dashboard_payload=dashboard_payload,
        top_n=top_n,
        enable_external_search=enable_external_search,
        target_date=target_date,
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2, default=str)
    return payload
