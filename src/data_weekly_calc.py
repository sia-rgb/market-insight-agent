from __future__ import annotations

from typing import Any

import pandas as pd

from .data_rules_config import get_metric_rule, load_metric_rule_mapping
from .utils_common import _coerce_bool


def add_week_fields(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce")
    out["week_start"] = out["date"] - pd.to_timedelta(out["date"].dt.weekday, unit="D")
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    return out


def _present_columns(df: pd.DataFrame, candidates: list[str]) -> list[str]:
    return [col for col in candidates if col in df.columns]


def _series_identity_columns(df: pd.DataFrame) -> list[str]:
    if "series_key" in df.columns and df["series_key"].fillna("").astype(str).ne("").any():
        return ["series_key"]

    preferred = _present_columns(df, ["source_sheet", "asset_key", "asset_class", "asset_name", "ticker", "metric_name"])
    if preferred:
        return preferred
    return _present_columns(df, ["asset_class", "asset_name", "ticker", "metric_name"])


def build_weekly_metrics(df: pd.DataFrame) -> pd.DataFrame:
    base = add_week_fields(df)
    base = base.sort_values("date")
    if "ticker" in base.columns:
        base["ticker"] = base["ticker"].fillna("")

    meta_cols = _present_columns(
        base,
        [
            "asset_class",
            "asset_name",
            "asset_key",
            "series_key",
            "ticker",
            "metric_name",
            "unit",
            "source_sheet",
            "source_file",
            "source_metric_name",
        ],
    )
    keys = ["week_start", "week_end", *meta_cols]
    observed_points = (
        base.groupby(keys, as_index=False, dropna=False)["value"].count().rename(columns={"value": "observed_points"})
    )
    weekly = base.groupby(keys, as_index=False, dropna=False).tail(1)
    weekly = weekly.rename(columns={"value": "current_week_value"})
    weekly = weekly[keys + ["current_week_value"]]
    weekly = weekly.merge(observed_points, on=keys, how="left")

    identity_cols = _series_identity_columns(weekly)
    weekly = weekly.sort_values([*identity_cols, "week_start"])
    weekly["expected_points"] = weekly.groupby(identity_cols)["observed_points"].cummax()
    weekly["data_coverage_ratio"] = (
        pd.to_numeric(weekly["observed_points"], errors="coerce")
        / pd.to_numeric(weekly["expected_points"], errors="coerce").replace(0, pd.NA)
    ).fillna(0.0)
    weekly["data_coverage_ratio"] = weekly["data_coverage_ratio"].clip(lower=0.0, upper=1.0)
    return weekly.reset_index(drop=True)


def build_weekly_changes(weekly_metrics: pd.DataFrame) -> pd.DataFrame:
    out = weekly_metrics.copy()
    identity_cols = _series_identity_columns(out)
    sort_keys = [*identity_cols, "week_start"]
    out = out.sort_values(sort_keys)

    out["previous_week_value"] = out.groupby(identity_cols)["current_week_value"].shift(1)
    out["abs_change"] = out["current_week_value"] - out["previous_week_value"]
    out["pct_change_pct"] = (out["abs_change"] / out["previous_week_value"]) * 100.0
    out.loc[out["previous_week_value"] == 0, "pct_change_pct"] = pd.NA

    out["direction"] = pd.NA
    out.loc[out["abs_change"] > 0, "direction"] = "up"
    out.loc[out["abs_change"] < 0, "direction"] = "down"

    out["calc_status"] = "ok"
    out.loc[out["previous_week_value"].isna(), "calc_status"] = "failed"
    out["calc_note"] = ""
    out.loc[out["previous_week_value"].isna(), "calc_note"] = "previous week missing"
    if "data_coverage_ratio" not in out.columns:
        out["data_coverage_ratio"] = 1.0
    return out


def bind_monitor_change_field(
    weekly_changes: pd.DataFrame,
    rules_cfg: dict[str, Any] | None = None,
    metric_rule_mapping_path: str | None = None,
) -> pd.DataFrame:
    out = weekly_changes.copy()
    binding_cfg: dict[str, Any] = {}
    if rules_cfg:
        binding_cfg = rules_cfg.get("monitor_change_binding", {})

    metric_mapping = load_metric_rule_mapping(metric_rule_mapping_path)
    metric_to_field = binding_cfg.get("metric_to_field", {})
    unit_to_field = binding_cfg.get("unit_to_field", {})
    keyword_to_field = binding_cfg.get("keyword_to_field", [])
    default_field = binding_cfg.get("default_field", "pct_change_pct")

    def choose_field(row: pd.Series) -> str:
        mapped = get_metric_rule(metric_mapping, row.get("source_sheet"), row.get("metric_name"))
        if mapped:
            field = str(mapped.get("monitor_change_field") or "").strip()
            if field in {"pct_change_pct", "abs_change"}:
                return field

        metric = str(row.get("metric_name", ""))
        if metric in metric_to_field:
            return metric_to_field[metric]

        unit = str(row.get("unit", ""))
        if unit in unit_to_field:
            return unit_to_field[unit]

        for item in keyword_to_field:
            keyword = str(item.get("keyword", ""))
            field = str(item.get("field", ""))
            if keyword and keyword in metric and field in {"pct_change_pct", "abs_change"}:
                return field
        return default_field if default_field in {"pct_change_pct", "abs_change"} else "pct_change_pct"

    def resolve_mapping(row: pd.Series) -> pd.Series:
        mapped = get_metric_rule(metric_mapping, row.get("source_sheet"), row.get("metric_name"))
        if not mapped:
            return pd.Series(
                {
                    "metric_mapping_found": False,
                    "include_in_anomaly": True,
                    "allowed_rule_ids": "",
                }
            )
        return pd.Series(
            {
                "metric_mapping_found": True,
                "include_in_anomaly": _coerce_bool(mapped.get("include_in_anomaly"), True),
                "allowed_rule_ids": "|".join(str(rule_id) for rule_id in mapped.get("rules", []) if str(rule_id).strip()),
            }
        )

    out["monitor_change_field"] = out.apply(choose_field, axis=1)
    mapping_meta = out.apply(resolve_mapping, axis=1)
    out["metric_mapping_found"] = mapping_meta["metric_mapping_found"]
    out["include_in_anomaly"] = mapping_meta["include_in_anomaly"]
    out["allowed_rule_ids"] = mapping_meta["allowed_rule_ids"]

    out["monitor_change_value"] = pd.NA
    out.loc[out["monitor_change_field"] == "pct_change_pct", "monitor_change_value"] = out["pct_change_pct"]
    out.loc[out["monitor_change_field"] == "abs_change", "monitor_change_value"] = out["abs_change"]
    return out
