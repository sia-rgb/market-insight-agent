from __future__ import annotations

from typing import Any

import pandas as pd

from .agent_evidence import build_driver_evidence, normalize_refs
from .utils_common import _row_join_key


def _rule_reason(rule_id: str) -> str:
    mapping = {
        "pct_change_abs_ge_metric_p95": "绝对涨跌幅高于该指标近52周95分位阈值",
        "abs_weekly_pct_ge_5_fallback": "绝对涨跌幅达到回退阈值（>=5%）",
        "fi_weekly_bp_ge_20": "周度变动超过20bp阈值",
        "amount_abs_change_ge_rolling_p90": "绝对变动高于近52周绝对变化90分位",
        "ratio_abs_change_ge_metric_p95": "比率类指标变动高于近52周95分位",
        "ratio_pp_change_ge_0_2_fallback": "比率类指标变动达到回退阈值（>=0.2）",
        "robust_z_abs_ge_3": "波动显著偏离历史稳健分布（robust z-score >= 3）",
        "global_top_movers_10": "本周全市场波动排名前10",
        "class_top_movers_3": "本周同资产类别波动排名前3",
        "hist_percentile_ge_95": "绝对变动位于该指标历史分位95%以上",
        "peer_percentile_ge_95": "绝对变动位于同类横截面分位95%以上",
    }
    return mapping.get(rule_id, f"触发规则 {rule_id}")


def _to_float(value: Any) -> float | None:
    val = pd.to_numeric(pd.Series([value]), errors="coerce").iloc[0]
    if pd.isna(val):
        return None
    return float(val)


def _to_percent(value: Any) -> float | None:
    val = _to_float(value)
    if val is None:
        return None
    if 0.0 <= val <= 1.0:
        return round(val * 100.0, 2)
    return round(val, 2)


def _build_ytd_position(row: dict[str, Any], weekly_changes: pd.DataFrame) -> dict[str, Any]:
    target_week = pd.to_datetime(row.get("week_start"), errors="coerce")
    if pd.isna(target_week):
        return {"available": False, "note": "year_week_missing"}

    field = str(row.get("monitor_change_field", ""))
    if field not in {"pct_change_pct", "abs_change"} or field not in weekly_changes.columns:
        return {"available": False, "note": "monitor_field_unavailable"}

    asset_name = str(row.get("asset_name", ""))
    metric_name = str(row.get("metric_name", ""))
    cur_val = _to_float(row.get("monitor_change_value"))
    pct_val = _to_float(row.get("pct_change_pct"))
    if cur_val is None and pct_val is None:
        return {"available": False, "note": "current_change_missing"}
    direction_val = pct_val if pct_val is not None else cur_val
    if direction_val is None:
        return {"available": False, "note": "direction_missing"}
    direction = "down" if direction_val < 0 else "up"

    wc = weekly_changes.copy()
    wc["week_start"] = pd.to_datetime(wc["week_start"], errors="coerce")
    series_key = str(row.get("series_key", "")).strip()
    asset_key = str(row.get("asset_key", "")).strip()
    if "series_key" in wc.columns and series_key:
        wc = wc[wc["series_key"].astype(str).eq(series_key)]
    elif "asset_key" in wc.columns and asset_key:
        wc = wc[
            wc["asset_key"].astype(str).eq(asset_key)
            & wc["metric_name"].astype(str).eq(metric_name)
        ]
    else:
        wc = wc[
            wc["asset_name"].astype(str).eq(asset_name)
            & wc["metric_name"].astype(str).eq(metric_name)
        ]
    wc = wc[(wc["week_start"].dt.year == target_week.year) & (wc["week_start"] <= target_week)]
    vals = pd.to_numeric(wc[field], errors="coerce").dropna()
    if direction == "down":
        vals = vals[vals < 0].abs()
        cur = abs(float(cur_val if cur_val is not None else direction_val))
        tag = "down_move"
    else:
        vals = vals[vals > 0].abs()
        cur = abs(float(cur_val if cur_val is not None else direction_val))
        tag = "up_move"
    if len(vals) == 0:
        return {"available": False, "note": "year_samples_empty"}
    rank = int((vals > cur).sum() + 1)
    total = int(len(vals))
    return {
        "available": True,
        "year": int(target_week.year),
        "direction_tag": tag,
        "rank": rank,
        "total": total,
        "is_year_extreme": rank == 1,
    }


def _build_agent_context(
    row: dict[str, Any],
    weekly_changes: pd.DataFrame,
    week_start: str,
    week_end: str,
    seed_refs: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    hist_pct = _to_percent(row.get("hist_percentile"))
    peer_pct = _to_percent(row.get("peer_percentile"))
    return {
        "task": "generate_asset_insight",
        "language": "zh-CN",
        "required_analysis_points": [
            "变化方向",
            "变化幅度",
            "数据驱动力分析",
        ],
        "time_window": {"week_start": week_start, "week_end": week_end},
        "asset_fact": {
            "asset_name": str(row.get("asset_name", "")),
            "asset_class": str(row.get("asset_class", "")),
            "asset_key": str(row.get("asset_key", "")),
            "series_key": str(row.get("series_key", "")),
            "metric_name": str(row.get("metric_name", "")),
            "unit": str(row.get("unit", "")),
            "current_week_value": _to_float(row.get("current_week_value")),
            "previous_week_value": _to_float(row.get("previous_week_value")),
            "pct_change_pct": _to_float(row.get("pct_change_pct")),
            "abs_change": _to_float(row.get("abs_change")),
            "monitor_change_field": str(row.get("monitor_change_field", "")),
            "monitor_change_value": _to_float(row.get("monitor_change_value")),
            "direction": str(row.get("direction", "")),
            "anomaly_rule_id": str(row.get("anomaly_rule_id", "")),
            "anomaly_rule_text": _rule_reason(str(row.get("anomaly_rule_id", ""))),
            "severity_score": _to_float(row.get("severity_score")),
            "hist_percentile_pct": hist_pct,
            "peer_percentile_pct": peer_pct,
            "robust_z_score": _to_float(row.get("robust_z_score")),
            "evidence_summary": str(row.get("evidence_summary", "")),
            "source_sheet": str(row.get("source_sheet", "")),
            "join_key": _row_join_key(row),
        },
        "historical_position": _build_ytd_position(row, weekly_changes),
        "external_evidence_seed": normalize_refs(seed_refs or []),
        "driver_evidence_seed": build_driver_evidence(seed_refs or [], evidence_type="seed"),
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
            "search_recency_days": 14,
        },
    }
