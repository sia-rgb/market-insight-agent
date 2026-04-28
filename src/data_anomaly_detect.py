from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from .data_rules_config import get_metric_rule, load_metric_rule_mapping, load_rules_config
from .utils_common import _coerce_bool


def _ready(df: pd.DataFrame, rules_cfg: dict[str, Any]) -> pd.DataFrame:
    out = df.copy()
    out["monitor_change_value"] = pd.to_numeric(out["monitor_change_value"], errors="coerce")
    out["abs_change"] = pd.to_numeric(out["abs_change"], errors="coerce")
    out["monitor_change_abs"] = out["monitor_change_value"].abs()

    guard = rules_cfg.get("invalid_guard", {})
    required_status = str(guard.get("calc_status_required", "ok"))
    min_cov = float(guard.get("min_data_coverage_ratio", 0.8))
    required_fields = guard.get("required_fields", ["asset_name", "metric_name", "monitor_change_field"])

    mask = out["calc_status"].astype(str).eq(required_status)
    if "data_coverage_ratio" in out.columns:
        mask &= pd.to_numeric(out["data_coverage_ratio"], errors="coerce").fillna(0) >= min_cov
    for col in required_fields:
        if col in out.columns:
            mask &= out[col].notna() & out[col].astype(str).ne("")
        else:
            mask &= False
    mask &= out["monitor_change_value"].notna()
    return out[mask].copy()


def _append_rule(base: pd.DataFrame, mask: pd.Series, rule_id: str, rule_type: str, label_up: str, label_down: str) -> pd.DataFrame:
    part = base[mask].copy()
    if part.empty:
        return part
    part["anomaly_rule_id"] = rule_id
    part["anomaly_rule_type"] = rule_type
    part["anomaly_label"] = np.where(part["direction"] == "down", label_down, label_up)
    return part


def _series_group_cols(df: pd.DataFrame) -> list[str]:
    if "series_key" in df.columns and df["series_key"].fillna("").astype(str).ne("").any():
        return ["series_key"]
    if all(col in df.columns for col in ["source_sheet", "asset_key", "metric_name"]):
        return ["source_sheet", "asset_key", "metric_name"]
    if all(col in df.columns for col in ["source_sheet", "asset_name", "metric_name"]):
        return ["source_sheet", "asset_name", "metric_name"]
    return ["asset_name", "metric_name"]


def _past_hist_percentile(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    out = np.full(len(values), np.nan, dtype=float)
    history: list[float] = []
    for idx, value in enumerate(values):
        if history and not np.isnan(value):
            hist = np.asarray(history, dtype=float)
            out[idx] = float((hist <= value).sum() / len(hist))
        if not np.isnan(value):
            history.append(float(value))
    return pd.Series(out, index=series.index)


def _past_robust_z(series: pd.Series) -> pd.Series:
    values = pd.to_numeric(series, errors="coerce").to_numpy(dtype=float)
    out = np.zeros(len(values), dtype=float)
    history: list[float] = []
    for idx, value in enumerate(values):
        if history and not np.isnan(value):
            hist = np.asarray(history, dtype=float)
            median = float(np.median(hist))
            mad = float(np.median(np.abs(hist - median)))
            if mad > 0:
                out[idx] = abs((float(value) - median) / mad)
        if not np.isnan(value):
            history.append(float(value))
    return pd.Series(out, index=series.index)


def _build_percentiles(df: pd.DataFrame, rules_cfg: dict[str, Any]) -> pd.DataFrame:
    series_group_cols = _series_group_cols(df)
    out = df.sort_values([*series_group_cols, "week_start"]).copy()
    stats_cfg = rules_cfg.get("stats", {})
    rolling_window = int(stats_cfg.get("rolling_window_weeks", 52))
    rolling_min = int(stats_cfg.get("rolling_min_periods", 8))

    out["history_count"] = out.groupby(series_group_cols).cumcount()
    out["peer_count"] = out.groupby(["week_start", "asset_class", "metric_name"])["asset_name"].transform("count")
    out["peer_percentile"] = out.groupby(["week_start", "asset_class", "metric_name"])["monitor_change_abs"].rank(pct=True)

    grp_abs = out.groupby(series_group_cols)["monitor_change_abs"]
    out["hist_percentile"] = grp_abs.transform(_past_hist_percentile)
    out["metric_rolling_52w_abs_p95"] = grp_abs.transform(
        lambda s: s.shift(1).rolling(window=rolling_window, min_periods=rolling_min).quantile(0.95)
    )

    grp_change = out.groupby(series_group_cols)["abs_change"]
    out["rolling_52w_abs_change_p90"] = grp_change.transform(
        lambda s: s.abs().shift(1).rolling(window=rolling_window, min_periods=rolling_min).quantile(0.90)
    )

    grp_value = out.groupby(series_group_cols)["monitor_change_value"]
    out["robust_z_score"] = grp_value.transform(_past_robust_z).fillna(0.0)
    return out


def _contains_keywords(series: pd.Series, keywords: list[str]) -> pd.Series:
    as_text = series.fillna("").astype(str)
    mask = pd.Series(False, index=series.index)
    for kw in keywords:
        if kw:
            mask |= as_text.str.contains(kw, case=False, regex=False)
    return mask


def _rule_base_mask(base: pd.DataFrame, rule: dict[str, Any], rules_cfg: dict[str, Any]) -> pd.Series:
    mask = pd.Series(True, index=base.index)

    monitor_field = rule.get("monitor_change_field")
    if monitor_field:
        mask &= base["monitor_change_field"].astype(str).eq(str(monitor_field))

    if rule.get("asset_class_equals"):
        mask &= base["asset_class"].astype(str).eq(str(rule["asset_class_equals"]))
    if rule.get("unit_equals"):
        mask &= base["unit"].astype(str).eq(str(rule["unit_equals"]))
    if rule.get("exclude_asset_class"):
        exclude = {str(x) for x in rule.get("exclude_asset_class", [])}
        mask &= ~base["asset_class"].astype(str).isin(exclude)

    metric_group = rule.get("metric_group")
    if metric_group:
        groups = rules_cfg.get("metric_groups", {})
        keywords = [str(x) for x in groups.get(metric_group, [])]
        mask &= _contains_keywords(base["metric_name"], keywords)

    min_history = rule.get("min_history_weeks")
    if min_history is not None:
        mask &= pd.to_numeric(base["history_count"], errors="coerce").fillna(0) >= int(min_history)
    only_when_lt = rule.get("only_when_history_lt_weeks")
    if only_when_lt is not None:
        mask &= pd.to_numeric(base["history_count"], errors="coerce").fillna(0) < int(only_when_lt)
    min_peer_count = rule.get("min_peer_count")
    if min_peer_count is not None:
        mask &= pd.to_numeric(base["peer_count"], errors="coerce").fillna(0) >= int(min_peer_count)

    comparison = str(rule.get("comparison", ""))
    field = str(rule.get("field", "monitor_change_value"))
    val = pd.to_numeric(base[field], errors="coerce")
    if comparison == "abs_ge_value":
        mask &= val.abs() >= float(rule.get("threshold_value", 0))
    elif comparison == "ge_value":
        mask &= val >= float(rule.get("threshold_value", 0))
    elif comparison == "abs_ge_field":
        threshold_field = str(rule.get("threshold_field", ""))
        thr = pd.to_numeric(base.get(threshold_field, pd.Series(np.nan, index=base.index)), errors="coerce")
        mask &= thr.notna() & (val.abs() >= thr)
    return mask


def _apply_metric_mapping(base: pd.DataFrame, metric_rule_mapping_path: str | None) -> pd.DataFrame:
    out = base.copy()
    mapping = load_metric_rule_mapping(metric_rule_mapping_path)
    if not mapping:
        if "metric_mapping_found" not in out.columns:
            out["metric_mapping_found"] = False
        if "include_in_anomaly" not in out.columns:
            out["include_in_anomaly"] = True
        if "allowed_rule_ids" not in out.columns:
            out["allowed_rule_ids"] = ""
        return out

    def resolve(row: pd.Series) -> pd.Series:
        mapped = get_metric_rule(mapping, row.get("source_sheet"), row.get("metric_name"))
        if not mapped:
            return pd.Series(
                {
                    "metric_mapping_found": _coerce_bool(row.get("metric_mapping_found"), False),
                    "include_in_anomaly": _coerce_bool(row.get("include_in_anomaly"), True),
                    "allowed_rule_ids": str(row.get("allowed_rule_ids", "")).strip(),
                    "mapped_monitor_change_field": "",
                }
            )
        return pd.Series(
            {
                "metric_mapping_found": True,
                "include_in_anomaly": _coerce_bool(mapped.get("include_in_anomaly"), True),
                "allowed_rule_ids": "|".join(str(rule_id) for rule_id in mapped.get("rules", []) if str(rule_id).strip()),
                "mapped_monitor_change_field": str(mapped.get("monitor_change_field") or "").strip(),
            }
        )

    resolved = out.apply(resolve, axis=1)
    out["metric_mapping_found"] = resolved["metric_mapping_found"]
    out["include_in_anomaly"] = resolved["include_in_anomaly"]
    out["allowed_rule_ids"] = resolved["allowed_rule_ids"]

    mapped_field = resolved["mapped_monitor_change_field"]
    has_field_override = mapped_field.astype(str).isin({"pct_change_pct", "abs_change"})
    out.loc[has_field_override, "monitor_change_field"] = mapped_field.loc[has_field_override]
    out.loc[out["monitor_change_field"] == "pct_change_pct", "monitor_change_value"] = out["pct_change_pct"]
    out.loc[out["monitor_change_field"] == "abs_change", "monitor_change_value"] = out["abs_change"]

    include_mask = out["include_in_anomaly"].map(lambda value: _coerce_bool(value, True))
    return out[include_mask].copy()


def _rule_allowed_mask(base: pd.DataFrame, rule_id: str) -> pd.Series:
    if "metric_mapping_found" not in base.columns or "allowed_rule_ids" not in base.columns:
        return pd.Series(True, index=base.index)

    mapping_found = base["metric_mapping_found"].map(lambda value: _coerce_bool(value, False))
    allowed = base["allowed_rule_ids"].fillna("").astype(str)
    allowed_mask = allowed.map(lambda raw: rule_id in {item for item in raw.split("|") if item})
    return (~mapping_found) | allowed_mask


def _apply_single_rule(base: pd.DataFrame, rule: dict[str, Any], rules_cfg: dict[str, Any]) -> pd.DataFrame:
    rule_id = str(rule.get("rule_id", ""))
    rule_type = str(rule.get("rule_type", ""))
    if not rule_id or not bool(rule.get("enabled", True)):
        return pd.DataFrame()

    label_up = str(rule.get("label_up", rule_id))
    label_down = str(rule.get("label_down", label_up))
    allowed_mask = _rule_allowed_mask(base, rule_id)

    if rule_type == "ranking":
        scope = [str(x) for x in rule.get("rank_scope", ["week_start"])]
        top_n = int(rule.get("top_n", 0))
        if top_n <= 0:
            return pd.DataFrame()
        tmp = base.copy()
        rank_col = f"rank__{rule_id}"
        tmp[rank_col] = tmp.groupby(scope)["monitor_change_abs"].rank(ascending=False, method="min")
        return _append_rule(tmp, allowed_mask & (tmp[rank_col] <= top_n), rule_id, rule_type, label_up, label_down)

    mask = _rule_base_mask(base, rule, rules_cfg)
    return _append_rule(base, allowed_mask & mask, rule_id, rule_type, label_up, label_down)


def _build_severity(out: pd.DataFrame, rules_cfg: dict[str, Any]) -> pd.Series:
    weights = rules_cfg.get("severity", {}).get("weights", {})
    w_adapt = float(weights.get("adaptive_threshold_score", 0.35))
    w_robust = float(weights.get("robust_z_score_norm", 0.25))
    w_peer = float(weights.get("peer_score", 0.20))
    w_rank = float(weights.get("ranking_score", 0.10))
    w_hist = float(weights.get("hist_score", 0.10))

    threshold_field_by_rule: dict[str, str] = {}
    for rule in rules_cfg.get("rules", []):
        if rule.get("comparison") == "abs_ge_field":
            threshold_field_by_rule[str(rule.get("rule_id", ""))] = str(rule.get("threshold_field", ""))

    adaptive = pd.Series(0.0, index=out.index)
    for rule_id, threshold_field in threshold_field_by_rule.items():
        idx = out["anomaly_rule_id"].astype(str).eq(rule_id)
        if threshold_field and threshold_field in out.columns:
            thr = pd.to_numeric(out.loc[idx, threshold_field], errors="coerce")
            val = pd.to_numeric(out.loc[idx, "monitor_change_value"], errors="coerce").abs()
            score = ((val / thr.replace(0, np.nan)) * 100.0).clip(lower=0, upper=100).fillna(0)
            adaptive.loc[idx] = score

    robust = (pd.to_numeric(out["robust_z_score"], errors="coerce").abs() / 5.0 * 100.0).clip(lower=0, upper=100).fillna(0)
    peer = (pd.to_numeric(out["peer_percentile"], errors="coerce").fillna(0) * 100.0).clip(lower=0, upper=100)
    hist = (pd.to_numeric(out["hist_percentile"], errors="coerce").fillna(0) * 100.0).clip(lower=0, upper=100)

    g_rank = out.groupby("week_start")["monitor_change_abs"].rank(ascending=False, method="min")
    c_rank = out.groupby(["week_start", "asset_class"])["monitor_change_abs"].rank(ascending=False, method="min")
    g_score = (100 / g_rank.replace(0, np.nan)).clip(lower=0, upper=100).fillna(0)
    c_score = (100 / c_rank.replace(0, np.nan)).clip(lower=0, upper=100).fillna(0)
    ranking = ((g_score + c_score) / 2.0).clip(lower=0, upper=100)

    score = w_adapt * adaptive + w_robust * robust + w_peer * peer + w_rank * ranking + w_hist * hist
    return score.clip(lower=0, upper=100)


def _candidate_dedup_cols(df: pd.DataFrame) -> list[str]:
    if "series_key" in df.columns and df["series_key"].fillna("").astype(str).ne("").any():
        return ["week_start", "series_key", "anomaly_rule_id"]
    if all(col in df.columns for col in ["source_sheet", "asset_name", "metric_name"]):
        return ["week_start", "source_sheet", "asset_name", "metric_name", "anomaly_rule_id"]
    return ["week_start", "asset_name", "metric_name", "anomaly_rule_id"]


def build_anomaly_candidates(
    weekly_changes: pd.DataFrame,
    rules_cfg_path: str | None = None,
    metric_rule_mapping_path: str | None = None,
) -> pd.DataFrame:
    keep_cols = [
        "week_start",
        "week_end",
        "asset_class",
        "asset_name",
        "asset_key",
        "series_key",
        "ticker",
        "metric_name",
        "unit",
        "source_sheet",
        "current_week_value",
        "previous_week_value",
        "abs_change",
        "pct_change_pct",
        "direction",
        "monitor_change_field",
        "monitor_change_value",
        "anomaly_rule_id",
        "anomaly_rule_type",
        "anomaly_label",
        "severity_score",
        "evidence_summary",
        "hist_percentile",
        "peer_percentile",
        "robust_z_score",
    ]
    rules_cfg = load_rules_config(rules_cfg_path)
    base = _ready(weekly_changes, rules_cfg)
    base = _apply_metric_mapping(base, metric_rule_mapping_path)
    if base.empty:
        return pd.DataFrame(columns=keep_cols)

    base = _build_percentiles(base, rules_cfg)
    candidates: list[pd.DataFrame] = []
    for rule in rules_cfg.get("rules", []):
        hit = _apply_single_rule(base, rule, rules_cfg)
        if not hit.empty:
            candidates.append(hit)

    if not candidates:
        return pd.DataFrame(columns=keep_cols)

    out = pd.concat(candidates, ignore_index=True)
    out["severity_score"] = _build_severity(out, rules_cfg)
    out["evidence_summary"] = (
        "change="
        + out["monitor_change_value"].round(4).astype(str)
        + "; field="
        + out["monitor_change_field"].astype(str)
        + "; rule="
        + out["anomaly_rule_id"].astype(str)
    )

    for col in keep_cols:
        if col not in out.columns:
            out[col] = pd.NA

    out = out[keep_cols].drop_duplicates(subset=_candidate_dedup_cols(out))
    return out.reset_index(drop=True)
