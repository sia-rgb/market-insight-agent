from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd

from .agent_context import _build_agent_context, _row_join_key
from .agent_evidence import normalize_refs
from .agent_llm import _generate_insight_with_llm
from .agent_runtime import log_event


def rank_abnormal_assets(anomaly_candidates: pd.DataFrame, top_n: int = 10) -> list[dict[str, Any]]:
    if anomaly_candidates.empty:
        return []
    ranked = anomaly_candidates.sort_values("severity_score", ascending=False)
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for row in ranked.to_dict("records"):
        key = _row_join_key(row)
        if key in seen:
            continue
        seen.add(key)
        out.append(row)
        if len(out) >= top_n:
            break
    return out


def _adapt_report_insights_payload(payload: dict[str, Any]) -> dict[str, Any]:
    out = dict(payload)
    norm_top_assets: list[dict[str, Any]] = []
    for asset in (out.get("top_abnormal_assets", []) or []):
        if not isinstance(asset, dict):
            continue
        norm_asset = dict(asset)
        norm_asset["asset_name"] = str(asset.get("asset_name", "")).strip()
        norm_asset["asset_class"] = str(asset.get("asset_class", "")).strip()
        norm_asset["asset_key"] = str(asset.get("asset_key", "")).strip()
        norm_asset["series_key"] = str(asset.get("series_key", "")).strip()
        norm_asset["metric_name"] = str(asset.get("metric_name", "")).strip()
        norm_asset["source_sheet"] = str(asset.get("source_sheet", "")).strip()
        norm_asset["card_id"] = _row_join_key(norm_asset)
        norm_top_assets.append(norm_asset)
    out["top_abnormal_assets"] = norm_top_assets
    out["market_summary_paragraph"] = str(out.get("market_summary_paragraph", "")).strip()

    norm_cards: list[dict[str, Any]] = []
    for card in (out.get("key_asset_cards", []) or []):
        if not isinstance(card, dict):
            continue
        refs = card.get("external_references", []) or []
        if not isinstance(refs, list):
            refs = []
        norm_card = {
            "asset_name": str(card.get("asset_name", "")).strip(),
            "asset_class": str(card.get("asset_class", "")).strip(),
            "asset_key": str(card.get("asset_key", "")).strip(),
            "series_key": str(card.get("series_key", "")).strip(),
            "metric_name": str(card.get("metric_name", "")).strip(),
            "direction_summary": str(card.get("direction_summary", "")).strip(),
            "magnitude_summary": str(card.get("magnitude_summary", "")).strip(),
            "driver_analysis": str(card.get("driver_analysis", "")).strip(),
            "rule_ids": card.get("rule_ids", []) or [],
            "evidence_summary": str(card.get("evidence_summary", "")).strip(),
            "source_refs": card.get("source_refs", []) or [],
            "source_sheet": str(card.get("source_sheet", "")).strip(),
            "external_context_used": bool(card.get("external_context_used", False)),
            "driver_note": str(card.get("driver_note", "")).strip(),
            "external_references": refs,
            "driver_evidence": card.get("driver_evidence", []) or [],
        }
        norm_card["card_id"] = _row_join_key(norm_card)
        norm_cards.append(norm_card)
    out["key_asset_cards"] = norm_cards
    return out


def build_report_insights(
    week_start: str,
    top_n: int,
    anomaly_candidates: pd.DataFrame,
    weekly_changes: pd.DataFrame,
    enable_external_search: bool = True,
) -> dict[str, Any]:
    top_assets = rank_abnormal_assets(anomaly_candidates, top_n=top_n)

    key_cards: list[dict[str, Any]] = []
    external_refs: list[dict[str, Any]] = []
    query_log: list[dict[str, Any]] = []

    for row in top_assets:
        log_event(
            "asset_processing_started",
            asset_name=str(row.get("asset_name", "")).strip(),
            asset_class=str(row.get("asset_class", "")).strip(),
            metric_name=str(row.get("metric_name", "")).strip(),
            anomaly_rule_id=str(row.get("anomaly_rule_id", "")).strip(),
        )
        refs: list[dict[str, Any]] = []
        asset_context = _build_agent_context(
            row=row,
            weekly_changes=weekly_changes,
            week_start=week_start,
            week_end=str(row.get("week_end", "")),
            seed_refs=refs,
        )
        insight_gen = _generate_insight_with_llm(
            context=asset_context,
            allow_external_search=enable_external_search,
        )
        insight_refs = normalize_refs(insight_gen.get("external_references", []))
        driver_evidence = insight_gen.get("driver_evidence", []) or []
        query_log.extend(insight_gen.get("query_log", []))

        direction_summary = str(insight_gen.get("direction_summary", "")).strip()
        magnitude_summary = str(insight_gen.get("magnitude_summary", "")).strip()
        driver_analysis = (
            str(insight_gen.get("driver_analysis", "")).strip()
            or "内部数据已显示该指标本周触发异常变动；后续重点观察相关政策、资金面、市场评论与同类资产表现是否同步变化。"
        )

        if not direction_summary and not magnitude_summary:
            asset_fact = asset_context.get("asset_fact") or {}
            direction = str(asset_fact.get("direction", "")).strip()
            direction_text = "上行" if direction == "up" else "下行" if direction == "down" else "方向待确认"
            direction_summary = f"{asset_fact.get('asset_name', '')} {asset_fact.get('metric_name', '')} 本周呈{direction_text}态势。"
        if not magnitude_summary:
            magnitude_summary = "变化幅度处于历史与横向分位的高位区间。"

        card = {
            "asset_name": row.get("asset_name", ""),
            "asset_class": row.get("asset_class", ""),
            "asset_key": row.get("asset_key", ""),
            "series_key": row.get("series_key", ""),
            "metric_name": row.get("metric_name", ""),
            "direction_summary": direction_summary,
            "magnitude_summary": magnitude_summary,
            "driver_analysis": driver_analysis,
            "rule_ids": [row.get("anomaly_rule_id", "")],
            "evidence_summary": row.get("evidence_summary", ""),
            "source_refs": [f"{row.get('source_sheet', '')}"] if row.get("source_sheet") else [],
            "source_sheet": row.get("source_sheet", ""),
            "external_context_used": bool(insight_refs),
            "driver_note": str(insight_gen.get("driver_note", "")).strip() or "llm_json_output",
            "external_references": insight_refs,
            "driver_evidence": driver_evidence,
        }
        card["card_id"] = _row_join_key(card)
        external_refs.extend(insight_refs)
        key_cards.append(card)

    insight_status = "ok" if top_assets else "insufficient_data"
    market_summary = "本周市场出现多资产波动，重点见异常资产卡片。" if top_assets else "本周有效异常样本不足。"
    payload = {
        "run_id": datetime.now(timezone.utc).strftime("run_%Y%m%d_%H%M%S"),
        "week_start": week_start,
        "top_abnormal_assets": top_assets,
        "key_asset_cards": key_cards,
        "market_summary_paragraph": market_summary,
        "insight_status": insight_status,
        "external_context_used": any(card["external_context_used"] for card in key_cards),
        "external_references": external_refs,
        "search_query_log": query_log,
    }
    return _adapt_report_insights_payload(payload)
