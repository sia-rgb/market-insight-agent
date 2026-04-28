from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


def load_pipeline_contract(path: str | None = None) -> dict[str, Any]:
    contract_path = Path(path or "config/pipeline_contract.yaml")
    if not contract_path.exists():
        raise FileNotFoundError(f"pipeline contract not found: {contract_path}")

    with contract_path.open("r", encoding="utf-8") as f:
        loaded = yaml.safe_load(f) or {}

    pipeline_contract = loaded.get("pipeline_contract")
    if not isinstance(pipeline_contract, dict):
        raise ValueError("pipeline contract payload is missing 'pipeline_contract'")
    if not isinstance(pipeline_contract.get("steps"), list):
        raise ValueError("pipeline contract must define a step list")
    return pipeline_contract


def get_pipeline_step_names(contract: dict[str, Any]) -> list[str]:
    return [str(step.get("step_name", "")).strip() for step in contract.get("steps", []) if str(step.get("step_name", "")).strip()]


def get_artifact_filenames(contract: dict[str, Any]) -> dict[str, str]:
    return dict(contract.get("artifact_filenames", {}))
