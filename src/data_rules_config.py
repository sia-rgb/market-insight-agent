from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .utils_common import _safe_str, _as_list

REQUIRED_TOP_LEVEL_KEYS = {
    "monitor_change_binding",
    "invalid_guard",
    "metric_groups",
    "stats",
    "rules",
    "severity",
}

VALID_MONITOR_CHANGE_FIELDS = {"pct_change_pct", "abs_change"}


def load_rules_config(rules_cfg_path: str | None) -> dict[str, Any]:
    path = Path(rules_cfg_path or "config/rules_config.yaml")
    if not path.exists():
        raise FileNotFoundError(f"rules config not found: {path}")

    with path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    missing = sorted(REQUIRED_TOP_LEVEL_KEYS.difference(loaded.keys()))
    if missing:
        raise ValueError(f"rules config missing required keys: {', '.join(missing)}")

    if not isinstance(loaded.get("rules"), list):
        raise ValueError("rules config field 'rules' must be a list")

    return loaded


def load_metric_rule_mapping(path: str | None = None) -> dict[tuple[str, str], dict[str, Any]]:
    cfg_path = Path(path or "config/metric_rule_mapping.yaml")
    if not cfg_path.exists():
        return {}

    with cfg_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    out: dict[tuple[str, str], dict[str, Any]] = {}
    for raw_entry in loaded.get("metric_rule_mapping", []):
        entry = raw_entry or {}
        sheet = _safe_str(entry.get("sheet"))
        if not sheet:
            continue

        raw_field = _safe_str(entry.get("monitor_change_field"))
        field = raw_field if raw_field in VALID_MONITOR_CHANGE_FIELDS else None
        rules = [_safe_str(rule_id) for rule_id in _as_list(entry.get("rules")) if _safe_str(rule_id)]
        include_in_anomaly = bool(entry.get("include_in_anomaly", True))

        for metric_name in _as_list(entry.get("metric_name")):
            out[(sheet, metric_name)] = {
                "sheet": sheet,
                "metric_name": metric_name,
                "monitor_change_field": field,
                "rules": rules,
                "include_in_anomaly": include_in_anomaly,
            }
    return out


def get_metric_rule(
    mapping: dict[tuple[str, str], dict[str, Any]] | None,
    source_sheet: Any,
    metric_name: Any,
) -> dict[str, Any] | None:
    if not mapping:
        return None
    key = (_safe_str(source_sheet), _safe_str(metric_name))
    if not all(key):
        return None
    return mapping.get(key)
