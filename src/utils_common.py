from __future__ import annotations

from typing import Any


def _safe_str(value: Any) -> str:
    if value is None:
        return ""
    try:
        import pandas as pd

        if pd.isna(value):
            return ""
    except Exception:
        pass
    return str(value).strip()


def _as_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [_safe_str(v) for v in value if _safe_str(v)]
    text = _safe_str(value)
    return [text] if text else []


def _row_join_key(row: dict[str, Any]) -> str:
    series_key = str(row.get("series_key", "")).strip()
    if series_key:
        return series_key
    asset_key = str(row.get("asset_key", "")).strip()
    metric_name = str(row.get("metric_name", "")).strip()
    if asset_key and metric_name:
        return f"{asset_key}::{metric_name}"
    return f"{str(row.get('asset_name', '')).strip()}::{metric_name}"


def _coerce_bool(value: Any, default: bool) -> bool:
    try:
        import pandas as pd

        if pd.isna(value):
            return default
    except Exception:
        if value is None:
            return default
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "y"}:
        return True
    if text in {"false", "0", "no", "n"}:
        return False
    return default
