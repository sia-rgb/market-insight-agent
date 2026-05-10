from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import re
from typing import Any

import pandas as pd
import yaml

from .utils_common import _safe_str, _as_list

DATE_KEYS = {"date", "Date", "end_date", "截止日期", "截止日"}
GLOBAL_INDEX_METRIC_ALIASES = {
    "周变动": "最近一周",
    "月变动": "最近1月",
    "YTD变动": "2026年至今",
    "YTD至今": "2026年至今",
    "年初至今": "2026年至今",
}
VALIDATION_OK = "ok"
HEADER_SCAN_MAX_ROWS = 30
DATA_START_OFFSET = 2
TICKER_COLUMN_NON_NUMERIC_MAX_RATIO = 0.5
GENERIC_METRIC_LABELS = {"close", "EDBclose", "收盘价", "成交额", "amt", "日期"}


@dataclass
class SheetContract:
    sheet: str
    asset_class: str
    status: str
    time_field: str | list[str] | None
    asset_field: str | list[str] | None
    value_fields: list[str]
    unit_rules: dict[str, Any]
    date_parse_rule: dict[str, Any]
    asset_key_rule: dict[str, Any]





def _make_unique_columns(columns: list[str]) -> list[str]:
    counts: dict[str, int] = {}
    unique: list[str] = []
    for col in columns:
        key = col or "unnamed"
        counts[key] = counts.get(key, 0) + 1
        unique.append(key if counts[key] == 1 else f"{key}__{counts[key]}")
    return unique


def _normalize_numeric(series: pd.Series) -> pd.Series:
    return pd.to_numeric(series.astype(str).str.replace(",", "", regex=False), errors="coerce")


def _normalize_a_share_turnover_value(sheet_name: str, metric_name: str, value: Any) -> Any:
    if sheet_name != "权益-A股交易量":
        return value
    if metric_name not in {"上证指数", "深证成指"}:
        return value
    if pd.isna(value):
        return value
    return value / 100000000


def _find_header_row(raw: pd.DataFrame) -> int | None:
    for i in range(min(HEADER_SCAN_MAX_ROWS, len(raw))):
        row_vals = {_safe_str(v) for v in raw.iloc[i].tolist()}
        if row_vals.intersection(DATE_KEYS):
            return i
    return None


def _block_starts(headers: list[str]) -> list[int]:
    return [i for i, h in enumerate(headers) if h in DATE_KEYS]


def _extract_unit_from_source_metric(source_metric_name: str) -> str:
    text = _safe_str(source_metric_name)
    if not text:
        return ""
    matches = re.findall(r"[（(]([^（）()]*)[）)]", text)
    if not matches:
        return ""
    return _safe_str(matches[-1])


def _is_unnamed_header(value: str) -> bool:
    text = _safe_str(value)
    return not text or text.lower().startswith("unnamed")


def _choose_metric_name(
    metric_col: str,
    source_metric_name: str,
    below_metric_name: str,
    upper_metric_name: str,
    allowed_metrics: set[str],
    metric_aliases: dict[str, str] | None = None,
) -> str:
    aliases = metric_aliases or {}

    def normalize(value: str) -> str:
        text = _safe_str(value)
        return aliases.get(text, text)

    candidates = [
        normalize(metric_col),
        normalize(source_metric_name),
        normalize(below_metric_name),
        normalize(upper_metric_name),
    ]
    if allowed_metrics:
        for cand in candidates:
            if cand in allowed_metrics:
                return cand
        if len(allowed_metrics) == 1:
            return next(iter(allowed_metrics))
        return ""

    for cand in candidates:
        if cand and not _is_unnamed_header(cand) and cand not in DATE_KEYS:
            return cand
    return ""


def _unit_source_name(*candidates: str) -> str:
    for cand in candidates:
        text = _safe_str(cand)
        if _extract_unit_from_source_metric(text):
            return text
    for cand in candidates:
        text = _safe_str(cand)
        if text:
            return text
    return ""


def _candidate_column_asset(metric_col: str, source_metric_name: str, upper_metric_name: str, metric_name: str) -> str:
    for cand in [_safe_str(source_metric_name), _safe_str(upper_metric_name), _safe_str(metric_col)]:
        if not cand or _is_unnamed_header(cand) or cand in DATE_KEYS or cand == metric_name:
            continue
        if cand in GENERIC_METRIC_LABELS or "收盘价" in cand:
            continue
        return cand
    return ""


def _to_date_value(value: Any, formats: list[str], allow_excel_serial: bool) -> pd.Timestamp:
    if pd.isna(value):
        return pd.NaT
    if isinstance(value, pd.Timestamp):
        return value.normalize()
    if isinstance(value, datetime):
        return pd.Timestamp(value).normalize()
    if allow_excel_serial and isinstance(value, (int, float)):
        # Excel serial day 1 is 1899-12-31, pandas origin uses 1899-12-30.
        try:
            return pd.to_datetime(float(value), unit="D", origin="1899-12-30").normalize()
        except Exception:
            return pd.NaT

    text = _safe_str(value)
    if not text:
        return pd.NaT

    for fmt in formats:
        try:
            return pd.Timestamp(datetime.strptime(text, fmt)).normalize()
        except ValueError:
            continue
    return pd.NaT


def _build_sheet_contract(raw: dict[str, Any], date_defaults: dict[str, Any]) -> SheetContract:
    date_parse_rule = dict(date_defaults)
    date_parse_rule.update(raw.get("date_parse_rule") or {})
    return SheetContract(
        sheet=_safe_str(raw.get("sheet")),
        asset_class=_safe_str(raw.get("asset_class")) or "unknown",
        status=_safe_str(raw.get("status")) or "ready",
        time_field=raw.get("time_field"),
        asset_field=raw.get("asset_field"),
        value_fields=_as_list(raw.get("value_fields")),
        unit_rules=raw.get("unit_rules") or {},
        date_parse_rule=date_parse_rule,
        asset_key_rule=raw.get("asset_key_rule") or {},
    )


def load_sheet_contracts_config(mapping_cfg_path: str | None) -> dict[str, Any]:
    path = Path(mapping_cfg_path or "config/sheet_contracts.yaml")
    if not path.exists():
        raise FileNotFoundError(f"sheet contracts not found: {path}")
    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    date_defaults = loaded.get("date_parse_defaults") or {}
    contracts: dict[str, SheetContract] = {}
    for item in loaded.get("sheet_contracts", []):
        contract = _build_sheet_contract(item or {}, date_defaults)
        if contract.sheet:
            contracts[contract.sheet] = contract

    return {
        "version": loaded.get("version", 1),
        "date_parse_defaults": date_defaults,
        "contracts": contracts,
    }


def load_excel_sheets(input_file: str) -> dict[str, pd.DataFrame]:
    excel = pd.ExcelFile(input_file)
    return {name: pd.read_excel(input_file, sheet_name=name, header=None) for name in excel.sheet_names}


def _resolve_asset_name(
    block: pd.DataFrame,
    row_idx: int,
    contract: SheetContract,
    ticker_col: str | None,
    column_asset_name: str = "",
) -> str:
    rule = contract.asset_key_rule or {}
    rule_type = _safe_str(rule.get("type")) or "prefer_columns"
    rule_cols = _as_list(rule.get("columns"))
    fallback = _safe_str(rule.get("fallback"))
    asset_fields = _as_list(contract.asset_field)

    def _from_col(col: str) -> str:
        return _safe_str(block.at[row_idx, col]) if col in block.columns else ""

    if column_asset_name and (rule_type != "fixed" or len(asset_fields) > 1):
        return column_asset_name

    if rule_type == "fixed":
        fixed = _safe_str(rule.get("value"))
        if fixed:
            return fixed
    elif rule_type == "column":
        for col in rule_cols:
            value = _from_col(col)
            if value:
                return value
    elif rule_type == "concat_columns":
        delimiter = _safe_str(rule.get("delimiter")) or "|"
        parts = [_from_col(col) for col in rule_cols]
        parts = [p for p in parts if p]
        if parts:
            return delimiter.join(parts)
    else:
        # prefer_columns
        for col in rule_cols:
            value = _from_col(col)
            if value:
                return value

    for field in asset_fields:
        value = _from_col(field)
        if value:
            return value
        if field and field not in block.columns:
            return field

    if ticker_col and ticker_col in block.columns:
        ticker = _safe_str(block.at[row_idx, ticker_col])
        if ticker:
            return ticker

    if fallback == "sheet_name":
        return contract.sheet
    return ""


def _standardize_snapshot_matrix(
    sheet_name: str,
    raw_df: pd.DataFrame,
    contract: SheetContract,
    source_file_name: str,
    metric_aliases: dict[str, str] | None = None,
) -> pd.DataFrame:
    header_row = None
    allowed_metrics = set(contract.value_fields or [])
    aliases = metric_aliases or {}
    for i in range(min(HEADER_SCAN_MAX_ROWS, len(raw_df))):
        row_vals = {aliases.get(_safe_str(v), _safe_str(v)) for v in raw_df.iloc[i].tolist()}
        if row_vals.intersection(allowed_metrics):
            header_row = i
            break
    if header_row is None:
        return pd.DataFrame()

    headers = [aliases.get(_safe_str(v), _safe_str(v)) for v in raw_df.iloc[header_row].tolist()]
    date_row_idx = header_row - 1 if header_row - 1 >= 0 else header_row
    date_headers = raw_df.iloc[date_row_idx].tolist()
    data = raw_df.iloc[header_row + 1 :].reset_index(drop=True).dropna(how="all")
    if data.empty:
        return pd.DataFrame()
    data.columns = _make_unique_columns(headers)

    parse_rule = contract.date_parse_rule or {}
    formats = _as_list(parse_rule.get("formats")) or ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    allow_excel_serial = bool(parse_rule.get("allow_excel_serial", True))
    parsed_header_dates = [_to_date_value(v, formats=formats, allow_excel_serial=allow_excel_serial) for v in date_headers]
    fallback_dates = [d for d in parsed_header_dates if not pd.isna(d)]
    fallback_date = max(fallback_dates) if fallback_dates else pd.NaT

    records: list[dict[str, Any]] = []
    asset_code_col = "Code" if "Code" in data.columns else ""
    asset_name_col = "Name" if "Name" in data.columns else asset_code_col

    for idx in data.index:
        asset_name = _safe_str(data.at[idx, asset_name_col]) if asset_name_col else ""
        asset_code = _safe_str(data.at[idx, asset_code_col]) if asset_code_col else asset_name
        if asset_code and not pd.isna(_to_date_value(asset_code, formats=formats, allow_excel_serial=allow_excel_serial)):
            continue
        if asset_name in GENERIC_METRIC_LABELS:
            continue
        if asset_name and not pd.isna(_normalize_numeric(pd.Series([asset_name])).iloc[0]):
            continue
        asset_key = _build_asset_key(contract, asset_code or asset_name)
        for col_idx, metric_name in enumerate(headers):
            metric_name = _safe_str(metric_name)
            if metric_name not in allowed_metrics or metric_name not in data.columns:
                continue
            value = _normalize_numeric(pd.Series([data.at[idx, metric_name]])).iloc[0]
            value = _normalize_a_share_turnover_value(sheet_name, metric_name, value)
            metric_date = parsed_header_dates[col_idx] if col_idx < len(parsed_header_dates) else pd.NaT
            if pd.isna(metric_date):
                metric_date = fallback_date
            unit, unit_ok = _resolve_unit(contract, metric_name, metric_name)
            record = {
                "date": metric_date,
                "asset_class": contract.asset_class,
                "asset_name": asset_name or asset_code,
                "asset_key": asset_key,
                "series_key": f"{asset_key}::{metric_name}" if asset_key else "",
                "ticker": asset_code,
                "metric_name": metric_name,
                "value": value,
                "unit": unit,
                "source_file": source_file_name,
                "source_sheet": sheet_name,
                "source_asset_name": asset_name,
                "source_metric_name": metric_name,
                "value_raw": _safe_str(data.at[idx, metric_name]),
                "unit_raw": _extract_unit_from_source_metric(metric_name),
                "is_valid": True,
                "validation_code": VALIDATION_OK,
                "validation_note": "",
            }
            if pd.isna(record["date"]):
                _set_validation(record, "invalid_date")
            if not asset_key:
                _set_validation(record, "asset_key_build_failed")
            if pd.isna(record["value"]):
                _set_validation(record, "missing_required_fields")
            if not unit_ok:
                _set_validation(record, "unknown_unit", f"unit={unit}")
            records.append(record)

    if not records:
        return pd.DataFrame()
    out = pd.DataFrame(records)
    out["week_start"] = out["date"] - pd.to_timedelta(out["date"].dt.weekday, unit="D")
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    return out


def _standardize_global_index_history(
    sheet_name: str,
    raw_df: pd.DataFrame,
    contract: SheetContract,
    source_file_name: str,
) -> pd.DataFrame:
    close_row = None
    for i in range(min(HEADER_SCAN_MAX_ROWS, len(raw_df))):
        row_vals = [_safe_str(v).lower() for v in raw_df.iloc[i].tolist()]
        if row_vals.count("close") >= 2:
            close_row = i
            break
    if close_row is None:
        return pd.DataFrame()

    parse_rule = contract.date_parse_rule or {}
    formats = _as_list(parse_rule.get("formats")) or ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    allow_excel_serial = bool(parse_rule.get("allow_excel_serial", True))
    metric_name = "最新收盘价"
    unit, unit_ok = _resolve_unit(contract, metric_name, metric_name)
    data = raw_df.iloc[close_row + 1 :].reset_index(drop=True)
    records: list[dict[str, Any]] = []

    seen_value_columns: set[int] = set()
    for date_col in range(raw_df.shape[1] - 1):
        value_col = date_col + 1
        if value_col in seen_value_columns:
            continue
        if _safe_str(raw_df.iat[close_row, value_col]).lower() != "close":
            continue
        date_header = _safe_str(raw_df.iat[close_row, date_col]).lower()
        if date_header == "close":
            continue
        seen_value_columns.add(value_col)

        ticker = _safe_str(raw_df.iat[close_row - 2, value_col]) if close_row >= 2 else ""
        asset_name = _safe_str(raw_df.iat[close_row - 1, value_col]) if close_row >= 1 else ticker
        asset_key = _build_asset_key(contract, ticker or asset_name)
        series_key = f"{asset_key}::{metric_name}" if asset_key else ""
        parsed_dates = data.iloc[:, date_col].map(
            lambda x: _to_date_value(x, formats=formats, allow_excel_serial=allow_excel_serial)
        )
        values = _normalize_numeric(data.iloc[:, value_col])

        for idx in data.index:
            record = {
                "date": parsed_dates.loc[idx],
                "asset_class": contract.asset_class,
                "asset_name": asset_name or ticker,
                "asset_key": asset_key,
                "series_key": series_key,
                "ticker": ticker,
                "metric_name": metric_name,
                "value": values.loc[idx],
                "unit": unit,
                "source_file": source_file_name,
                "source_sheet": sheet_name,
                "source_asset_name": asset_name,
                "source_metric_name": "close",
                "value_raw": _safe_str(data.iat[idx, value_col]),
                "unit_raw": "",
                "is_valid": True,
                "validation_code": VALIDATION_OK,
                "validation_note": "",
            }
            if pd.isna(record["date"]):
                _set_validation(record, "invalid_date")
            if not asset_key:
                _set_validation(record, "asset_key_build_failed")
            if pd.isna(record["value"]):
                _set_validation(record, "missing_required_fields")
            if not unit_ok:
                _set_validation(record, "unknown_unit", f"unit={unit}")
            records.append(record)

    if not records:
        return pd.DataFrame()
    out = pd.DataFrame(records)
    out["week_start"] = out["date"] - pd.to_timedelta(out["date"].dt.weekday, unit="D")
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    return out


def _looks_like_snapshot_matrix(
    raw_df: pd.DataFrame,
    contract: SheetContract,
    metric_aliases: dict[str, str] | None = None,
) -> bool:
    allowed_metrics = set(contract.value_fields or [])
    aliases = metric_aliases or {}
    for i in range(min(HEADER_SCAN_MAX_ROWS, len(raw_df))):
        row_vals = {aliases.get(_safe_str(v), _safe_str(v)) for v in raw_df.iloc[i].tolist()}
        if {"Code", "Name"}.issubset(row_vals) and row_vals.intersection(allowed_metrics):
            return True
    return False


def _build_asset_key(contract: SheetContract, asset_name: str) -> str:
    if not asset_name:
        return ""
    return f"{contract.sheet}::{asset_name}"


def _resolve_unit(contract: SheetContract, metric_name: str, source_metric_name: str) -> tuple[str, bool]:
    unit_rules = contract.unit_rules or {}
    metric_units = unit_rules.get("metric_units") or {}
    default_unit = _safe_str(unit_rules.get("default_unit")) or "raw"
    allowed_units = {_safe_str(v) for v in (unit_rules.get("allowed_units") or []) if _safe_str(v)}
    mapped_unit = _safe_str(metric_units.get(metric_name))
    parsed_unit = _extract_unit_from_source_metric(source_metric_name)
    unit = mapped_unit or parsed_unit or default_unit

    if allowed_units and unit not in allowed_units:
        return unit, False
    return unit, True


def _parse_date_series(block: pd.DataFrame, contract: SheetContract, fallback_date_col: str) -> pd.Series:
    parse_rule = contract.date_parse_rule or {}
    priority = _as_list(parse_rule.get("source_fields_priority"))
    if not priority:
        priority = _as_list(contract.time_field) or [fallback_date_col]

    source_col = ""
    for cand in priority:
        if cand in block.columns:
            source_col = cand
            break
    if not source_col:
        source_col = fallback_date_col

    formats = _as_list(parse_rule.get("formats")) or ["%Y-%m-%d", "%Y/%m/%d", "%Y%m%d"]
    allow_excel_serial = bool(parse_rule.get("allow_excel_serial", True))
    return block[source_col].map(lambda x: _to_date_value(x, formats=formats, allow_excel_serial=allow_excel_serial))


def _set_validation(record: dict[str, Any], code: str, note: str = "") -> None:
    if record.get("validation_code") == VALIDATION_OK:
        record["validation_code"] = code
        record["validation_note"] = note or code
        record["is_valid"] = False


def standardize_sheet(
    sheet_name: str,
    raw_df: pd.DataFrame,
    mapping_cfg: dict[str, Any],
    source_file_name: str = "market-data-auto.xlsx",
) -> pd.DataFrame:
    contracts: dict[str, SheetContract] = mapping_cfg.get("contracts", {})
    contract = contracts.get(sheet_name)
    if not contract or contract.status != "ready":
        return pd.DataFrame()

    global_index_aliases = GLOBAL_INDEX_METRIC_ALIASES if sheet_name == "权益-全球股指" else {}

    if sheet_name == "权益-全球股指":
        return _standardize_global_index_history(sheet_name, raw_df, contract, source_file_name)

    header_row = _find_header_row(raw_df)
    if header_row is None:
        return pd.DataFrame()

    headers = [_safe_str(v) for v in raw_df.iloc[header_row].tolist()]
    starts = _block_starts(headers)
    if not starts:
        return pd.DataFrame()

    cn_row_idx = header_row - 1 if header_row - 1 >= 0 else header_row
    cn_headers = [_safe_str(v) for v in raw_df.iloc[cn_row_idx].tolist()]
    below_row_idx = header_row + 1 if header_row + 1 < len(raw_df) else header_row
    below_headers = [_safe_str(v) for v in raw_df.iloc[below_row_idx].tolist()]
    upper_row_idx = header_row - 2 if header_row - 2 >= 0 else header_row
    upper_headers = [_safe_str(v) for v in raw_df.iloc[upper_row_idx].tolist()]
    upper_is_context = upper_row_idx != header_row
    data = raw_df.iloc[header_row + DATA_START_OFFSET :].reset_index(drop=True)

    records: list[dict[str, Any]] = []
    starts_with_end = starts[1:] + [len(headers)]

    for start, end in zip(starts, starts_with_end):
        block = data.iloc[:, start:end].copy()
        if block.shape[1] < 2:
            continue

        raw_block_headers = headers[start:end]
        block.columns = _make_unique_columns(raw_block_headers)
        block = block.dropna(how="all")
        if block.empty:
            continue

        date_col = headers[start]
        parsed_dates = _parse_date_series(block, contract, fallback_date_col=date_col)

        metric_start_idx = 1
        ticker_col = None
        if block.shape[1] >= 3:
            candidate = block.columns[1]
            numeric_ratio = _normalize_numeric(block[candidate]).notna().mean()
            if candidate and candidate not in DATE_KEYS and numeric_ratio < TICKER_COLUMN_NON_NUMERIC_MAX_RATIO:
                ticker_col = candidate
                metric_start_idx = 2

        allowed_metrics = set(contract.value_fields or [])
        for col_idx, metric_col in enumerate(block.columns[metric_start_idx:], start=metric_start_idx):
            metric_base = _safe_str(metric_col)
            raw_idx = start + col_idx
            source_metric_name = cn_headers[raw_idx] if raw_idx < len(cn_headers) else ""
            below_metric_name = below_headers[raw_idx] if raw_idx < len(below_headers) else ""
            upper_metric_name = upper_headers[raw_idx] if raw_idx < len(upper_headers) else ""
            metric_name = _choose_metric_name(
                metric_base,
                source_metric_name,
                below_metric_name,
                upper_metric_name,
                allowed_metrics,
                metric_aliases=global_index_aliases,
            )
            if not metric_name:
                continue

            value_series = _normalize_numeric(block[metric_col])
            if not value_series.notna().any():
                continue
            if sheet_name == "权益-A股交易量" and metric_name in {"上证指数", "深证成指"}:
                value_series = value_series / 100000000
            if upper_is_context and (metric_name == upper_metric_name or (
                len(allowed_metrics) == 1
                and metric_base != metric_name
                and source_metric_name != metric_name
                and below_metric_name != metric_name
            )):
                unit_source = _unit_source_name(upper_metric_name, metric_name)
            else:
                unit_source = _unit_source_name(source_metric_name, below_metric_name, upper_metric_name, metric_name)
            unit, unit_ok = _resolve_unit(contract, metric_name, unit_source)
            column_asset_name = _candidate_column_asset(metric_base, source_metric_name, upper_metric_name, metric_name)
            if len(_as_list(contract.asset_field)) > 1 and not ticker_col and not column_asset_name:
                continue

            for idx in block.index:
                record = {
                    "date": parsed_dates.loc[idx],
                    "asset_class": contract.asset_class,
                    "asset_name": "",
                    "asset_key": "",
                    "series_key": "",
                    "ticker": _safe_str(block.loc[idx, ticker_col]) if ticker_col else "",
                    "metric_name": metric_name,
                    "value": value_series.loc[idx],
                    "unit": unit,
                    "source_file": source_file_name,
                    "source_sheet": sheet_name,
                    "source_asset_name": _safe_str(block.loc[idx, ticker_col]) if ticker_col else "",
                    "source_metric_name": source_metric_name,
                    "value_raw": _safe_str(block.loc[idx, metric_col]),
                    "unit_raw": _extract_unit_from_source_metric(source_metric_name),
                    "is_valid": True,
                    "validation_code": VALIDATION_OK,
                    "validation_note": "",
                }

                asset_name = _resolve_asset_name(block, idx, contract, ticker_col, column_asset_name=column_asset_name)
                asset_key = _build_asset_key(contract, asset_name)
                series_key = f"{asset_key}::{metric_name}" if asset_key else ""
                record["asset_name"] = asset_name
                record["asset_key"] = asset_key
                record["series_key"] = series_key

                if pd.isna(record["date"]):
                    _set_validation(record, "invalid_date")
                if not asset_key:
                    _set_validation(record, "asset_key_build_failed")
                if pd.isna(record["value"]):
                    _set_validation(record, "missing_required_fields")
                if not unit_ok:
                    _set_validation(record, "unknown_unit", f"unit={unit}")

                records.append(record)

    if not records:
        return pd.DataFrame()

    out = pd.DataFrame(records)
    out["week_start"] = out["date"] - pd.to_timedelta(out["date"].dt.weekday, unit="D")
    out["week_end"] = out["week_start"] + pd.Timedelta(days=6)
    return out


def _deduplicate_records(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    key_cols = ["date", "source_sheet", "series_key"]
    for col in key_cols:
        if col not in df.columns:
            df[col] = pd.NA

    work = df.copy()
    work["__date_key"] = work["date"].map(lambda x: x.isoformat() if isinstance(x, pd.Timestamp) and not pd.isna(x) else "")
    work["__series_key"] = work["series_key"].astype(str).fillna("")
    work["__source_sheet"] = work["source_sheet"].astype(str).fillna("")
    group_cols = ["__date_key", "__source_sheet", "__series_key"]

    keep_rows: list[pd.Series] = []
    cmp_cols = ["asset_class", "asset_name", "asset_key", "metric_name", "value", "unit", "source_file"]

    for _, grp in work.groupby(group_cols, dropna=False):
        if len(grp) == 1:
            keep_rows.append(grp.iloc[0])
            continue

        valid_grp = grp[(grp["is_valid"] == True) & (grp["validation_code"] == VALIDATION_OK)]
        if len(valid_grp) == 1:
            keep_rows.append(valid_grp.iloc[0])
            continue

        normalized = grp[cmp_cols].astype(str).fillna("")
        first_row = grp.iloc[0].copy()
        if normalized.nunique(dropna=False).max() <= 1:
            keep_rows.append(first_row)
            continue

        first_row["is_valid"] = False
        first_row["validation_code"] = "duplicate_conflict"
        first_row["validation_note"] = "duplicate rows with conflicting values"
        keep_rows.append(first_row)

    out = pd.DataFrame(keep_rows).drop(columns=["__date_key", "__series_key", "__source_sheet"], errors="ignore")
    return out.reset_index(drop=True)


def validate_standardized_data(df: pd.DataFrame) -> pd.DataFrame:
    required = [
        "date",
        "week_start",
        "week_end",
        "asset_class",
        "asset_name",
        "metric_name",
        "value",
        "unit",
        "source_file",
        "source_sheet",
        "is_valid",
        "validation_code",
    ]
    out = df.copy()
    for col in required:
        if col not in out.columns:
            out[col] = pd.NA

    missing_any = out[["date", "asset_class", "asset_name", "metric_name", "value", "unit", "source_sheet"]].isna().any(axis=1)
    bad_rows = missing_any & (out["validation_code"] == VALIDATION_OK)
    out.loc[bad_rows, "is_valid"] = False
    out.loc[bad_rows, "validation_code"] = "missing_required_fields"
    out.loc[bad_rows, "validation_note"] = out.loc[bad_rows, "validation_note"].fillna("missing_required_fields")
    out.loc[out["validation_code"] == VALIDATION_OK, "validation_note"] = out.loc[
        out["validation_code"] == VALIDATION_OK, "validation_note"
    ].replace("", pd.NA)
    return out


def build_standardized_market_data(input_file: str, mapping_cfg_path: str | None) -> pd.DataFrame:
    mapping_cfg = load_sheet_contracts_config(mapping_cfg_path)
    sheets = load_excel_sheets(input_file)
    source_file_name = Path(input_file).name
    frames: list[pd.DataFrame] = []
    for sheet_name, raw in sheets.items():
        parsed = standardize_sheet(sheet_name, raw, mapping_cfg, source_file_name=source_file_name)
        if not parsed.empty:
            frames.append(parsed)
    if not frames:
        return pd.DataFrame()
    combined = pd.concat(frames, ignore_index=True)
    combined = _deduplicate_records(combined)
    return validate_standardized_data(combined)
