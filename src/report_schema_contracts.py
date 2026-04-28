from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

_REPORT_INSIGHTS_VALIDATOR: Draft202012Validator | None = None


def _load_report_insights_validator(schema_path: str | None = None) -> Draft202012Validator:
    global _REPORT_INSIGHTS_VALIDATOR
    if schema_path is None and _REPORT_INSIGHTS_VALIDATOR is not None:
        return _REPORT_INSIGHTS_VALIDATOR

    path = Path(schema_path or "schemas/report_insights.schema.json")
    if not path.exists():
        raise FileNotFoundError(f"report insights schema not found: {path}")
    schema = json.loads(path.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema)
    if schema_path is None:
        _REPORT_INSIGHTS_VALIDATOR = validator
    return validator


def validate_report_insights(payload: dict[str, Any], schema_path: str | None = None) -> None:
    validator = _load_report_insights_validator(schema_path)
    validator.validate(payload)
