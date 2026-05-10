from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd


DISPLAY_COLUMNS = [
    "date",
    "source_sheet",
    "asset_class",
    "asset_name",
    "asset_key",
    "series_key",
    "ticker",
    "metric_name",
    "value",
    "unit",
    "previous_date",
    "previous_value",
    "daily_abs_change",
    "daily_pct_change",
    "direction",
]

GLOBAL_INDEX_SOURCE_SHEET = "权益-全球股指"
GLOBAL_INDEX_CLOSE_METRIC = "最新收盘价"
GLOBAL_INDEX_CHANGE_OFFSETS = {
    "最近一周": 5,
    "最近1月": 22,
}
GLOBAL_INDEX_YTD_METRIC = "2026年至今"
GLOBAL_INDEX_YTD_BASE_DATE = pd.Timestamp("2026-01-05")


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _json_value(value: Any) -> Any:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except Exception:
        pass
    if isinstance(value, pd.Timestamp):
        return value.date().isoformat()
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            return value
    return value


def _to_record(row: pd.Series) -> dict[str, Any]:
    record: dict[str, Any] = {}
    for col in DISPLAY_COLUMNS:
        record[col] = _json_value(row[col]) if col in row.index else None
    return record


def _build_summary(df: pd.DataFrame, latest_df: pd.DataFrame) -> dict[str, Any]:
    return {
        "row_count": int(len(df)),
        "latest_row_count": int(len(latest_df)),
        "sheet_count": int(df["source_sheet"].nunique(dropna=True)) if "source_sheet" in df.columns else 0,
        "series_count": int(df["series_key"].nunique(dropna=True)) if "series_key" in df.columns else 0,
        "asset_count": int(df["asset_key"].nunique(dropna=True)) if "asset_key" in df.columns else 0,
        "asset_classes": sorted(_clean_text(v) for v in df["asset_class"].dropna().unique()) if "asset_class" in df.columns else [],
    }


def _build_sheet_summary(df: pd.DataFrame, latest_df: pd.DataFrame) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for sheet, grp in df.groupby("source_sheet", dropna=False):
        sheet_text = _clean_text(sheet)
        latest_grp = latest_df[latest_df["source_sheet"].astype(str) == sheet_text] if not latest_df.empty else pd.DataFrame()
        rows.append(
            {
                "source_sheet": sheet_text,
                "asset_class": _clean_text(grp["asset_class"].dropna().iloc[0]) if "asset_class" in grp.columns and grp["asset_class"].notna().any() else "",
                "series_count": int(grp["series_key"].nunique(dropna=True)),
                "latest_row_count": int(len(latest_grp)),
                "date_start": _json_value(grp["date"].min()),
                "date_end": _json_value(grp["date"].max()),
            }
        )
    return sorted(rows, key=lambda x: x["source_sheet"])


def _rank_records(df: pd.DataFrame, field: str, ascending: bool, top_n: int) -> list[dict[str, Any]]:
    if df.empty or field not in df.columns:
        return []
    ranked = df.dropna(subset=[field]).copy()
    if ranked.empty:
        return []
    ranked = ranked.sort_values(field, ascending=ascending).head(top_n)
    return [_to_record(row) for _, row in ranked.iterrows()]


def _build_rankings(latest_df: pd.DataFrame, top_n: int) -> dict[str, list[dict[str, Any]]]:
    abs_rank = latest_df.copy()
    if "daily_abs_change" in abs_rank.columns:
        abs_rank["abs_daily_abs_change"] = pd.to_numeric(abs_rank["daily_abs_change"], errors="coerce").abs()
    return {
        "top_gain_pct": _rank_records(latest_df, "daily_pct_change", ascending=False, top_n=top_n),
        "top_loss_pct": _rank_records(latest_df, "daily_pct_change", ascending=True, top_n=top_n),
        "top_abs_change": _rank_records(abs_rank, "abs_daily_abs_change", ascending=False, top_n=top_n),
    }


def _build_series(df: pd.DataFrame) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    identity_cols = ["series_key", "source_sheet", "asset_class", "asset_name", "asset_key", "ticker", "metric_name", "unit"]
    for series_key, grp in df.groupby("series_key", dropna=False):
        grp = grp.sort_values("date")
        first = grp.iloc[0]
        observations = []
        for _, row in grp.iterrows():
            observations.append(
                {
                    "date": _json_value(row["date"]),
                    "value": _json_value(row["value"]),
                    "previous_date": _json_value(row.get("previous_date")),
                    "previous_value": _json_value(row.get("previous_value")),
                    "daily_abs_change": _json_value(row.get("daily_abs_change")),
                    "daily_pct_change": _json_value(row.get("daily_pct_change")),
                    "direction": _json_value(row.get("direction")),
                }
            )
        item = {col: _json_value(first[col]) if col in first.index else None for col in identity_cols}
        item["series_key"] = _clean_text(series_key)
        item["observations"] = observations
        out.append(item)
    return sorted(out, key=lambda x: (_clean_text(x.get("source_sheet")), _clean_text(x.get("asset_name")), _clean_text(x.get("metric_name"))))


def _previous_available_date(df: pd.DataFrame, target_date: pd.Timestamp) -> pd.Timestamp:
    dates = sorted(v for v in df["date"].dropna().unique() if v < target_date)
    if not dates:
        return target_date
    return pd.Timestamp(dates[-1]).normalize()


def _previous_global_index_close_date(daily: pd.DataFrame, target_date: pd.Timestamp) -> pd.Timestamp:
    global_close = daily[
        (daily["source_sheet"].astype(str) == GLOBAL_INDEX_SOURCE_SHEET)
        & (daily["metric_name"].astype(str) == GLOBAL_INDEX_CLOSE_METRIC)
    ].copy()
    if global_close.empty:
        return _previous_available_date(daily, target_date)
    global_close["date"] = pd.to_datetime(global_close["date"], errors="coerce")
    global_close = global_close.dropna(subset=["date"])
    dates = sorted(
        v
        for v in global_close["date"].unique()
        if pd.Timestamp(v).normalize() < target_date and pd.Timestamp(v).weekday() < 5
    )
    if not dates:
        return _previous_available_date(daily, target_date)
    return pd.Timestamp(dates[-1]).normalize()


def _global_index_change_records(close_df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if close_df.empty:
        return records

    identity_cols = ["source_sheet", "asset_class", "asset_name", "asset_key", "ticker"]
    for _, grp in close_df.groupby("asset_key", dropna=False):
        grp = grp.sort_values("date").drop_duplicates("date", keep="last").reset_index(drop=True)
        if grp.empty:
            continue

        ytd_base = grp[grp["date"] <= GLOBAL_INDEX_YTD_BASE_DATE].tail(1)
        for idx, row in grp.iterrows():
            current_value = row["value"]
            base_rows: dict[str, pd.Series] = {}
            for metric_name, offset in GLOBAL_INDEX_CHANGE_OFFSETS.items():
                if idx >= offset:
                    base_rows[metric_name] = grp.iloc[idx - offset]
            if not ytd_base.empty and row["date"] >= GLOBAL_INDEX_YTD_BASE_DATE:
                base_rows[GLOBAL_INDEX_YTD_METRIC] = ytd_base.iloc[0]

            for metric_name, base_row in base_rows.items():
                base_value = base_row["value"]
                if pd.isna(current_value) or pd.isna(base_value) or base_value == 0:
                    continue
                asset_key = _clean_text(row.get("asset_key"))
                record = {col: row.get(col, "") for col in identity_cols}
                record.update(
                    {
                        "date": row["date"],
                        "series_key": f"{asset_key}::{metric_name}" if asset_key else "",
                        "metric_name": metric_name,
                        "value": round(float((current_value - base_value) / base_value), 4),
                        "unit": "%",
                    }
                )
                records.append(record)
    return records


def _append_global_index_change_metrics(df: pd.DataFrame) -> pd.DataFrame:
    metric_names = set(GLOBAL_INDEX_CHANGE_OFFSETS) | {GLOBAL_INDEX_YTD_METRIC}
    is_global_index = df["source_sheet"].astype(str) == GLOBAL_INDEX_SOURCE_SHEET
    is_derived_metric = df["metric_name"].astype(str).isin(metric_names)
    base_df = df[~(is_global_index & is_derived_metric)].copy()
    base_is_global_index = base_df["source_sheet"].astype(str) == GLOBAL_INDEX_SOURCE_SHEET
    close_df = base_df[base_is_global_index & (base_df["metric_name"].astype(str) == GLOBAL_INDEX_CLOSE_METRIC)].copy()
    records = _global_index_change_records(close_df)
    if not records:
        return base_df
    return pd.concat([base_df, pd.DataFrame(records)], ignore_index=True)


def _dashboard_scope_frame(daily: pd.DataFrame, target_date: pd.Timestamp) -> tuple[pd.DataFrame, pd.DataFrame, pd.Timestamp]:
    close_date = _previous_global_index_close_date(daily, target_date)
    scoped = daily[daily["date"] <= close_date].copy()
    latest_df = scoped[scoped["date"] == close_date].copy()
    return scoped, latest_df, close_date


def build_daily_dashboard_frame(standardized_data: pd.DataFrame) -> pd.DataFrame:
    required = {"date", "source_sheet", "series_key", "metric_name", "value", "unit"}
    missing = sorted(required.difference(standardized_data.columns))
    if missing:
        raise ValueError(f"standardized data missing required columns: {', '.join(missing)}")

    df = standardized_data.copy()
    if "is_valid" in df.columns:
        df = df[df["is_valid"].astype(str).str.lower() == "true"].copy()

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df["value"] = pd.to_numeric(df["value"], errors="coerce")
    df = df.dropna(subset=["date", "value"])
    df = df[df["series_key"].astype(str).str.strip() != ""].copy()
    df = _append_global_index_change_metrics(df)

    for col in DISPLAY_COLUMNS:
        if col not in df.columns:
            df[col] = ""

    df = df.sort_values(["series_key", "date"]).reset_index(drop=True)
    grouped = df.groupby("series_key", dropna=False)
    df["previous_date"] = grouped["date"].shift(1)
    df["previous_value"] = grouped["value"].shift(1)
    df["daily_abs_change"] = df["value"] - df["previous_value"]
    prev = df["previous_value"].replace(0, pd.NA)
    df["daily_pct_change"] = ((df["value"] - prev) / prev) * 100
    df["direction"] = "flat"
    df.loc[df["daily_abs_change"] > 0, "direction"] = "up"
    df.loc[df["daily_abs_change"] < 0, "direction"] = "down"
    df.loc[df["daily_abs_change"].isna(), "direction"] = "na"
    return df[DISPLAY_COLUMNS].reset_index(drop=True)


def build_dashboard_payload(
    standardized_data: pd.DataFrame,
    latest_date: str | None = None,
    top_n: int = 10,
) -> dict[str, Any]:
    daily = build_daily_dashboard_frame(standardized_data)
    if daily.empty:
        return {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "latest_date": "",
            "dates": [],
            "summary": _build_summary(daily, daily),
            "sheets": [],
            "latest_records": [],
            "rankings": {"top_gain_pct": [], "top_loss_pct": [], "top_abs_change": []},
            "series": [],
            "series_all": [],
        }

    requested = pd.to_datetime(latest_date, errors="coerce") if latest_date else pd.NaT
    if pd.isna(requested):
        target_date = daily["date"].max()
    else:
        target_date = requested.normalize()
    scoped_daily, latest_df, close_date = _dashboard_scope_frame(daily, target_date)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "latest_date": _json_value(target_date),
        "effective_close_date": _json_value(close_date),
        "dates": [_json_value(v) for v in sorted(scoped_daily["date"].dropna().unique())],
        "summary": _build_summary(scoped_daily, latest_df),
        "sheets": _build_sheet_summary(scoped_daily, latest_df),
        "latest_records": [_to_record(row) for _, row in latest_df.sort_values(["source_sheet", "asset_name", "metric_name"]).iterrows()],
        "rankings": _build_rankings(latest_df, top_n=top_n),
        "series": _build_series(scoped_daily),
        "series_all": _build_series(daily),
    }
