from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


_ENV_CACHE: dict[str, str] | None = None
logger = logging.getLogger(__name__)


def load_local_env() -> dict[str, str]:
    global _ENV_CACHE
    if _ENV_CACHE is not None:
        return _ENV_CACHE

    out: dict[str, str] = {}
    env_path = Path(".env")
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            key = k.strip().lstrip("\ufeff")
            out[key] = v.strip().strip('"').strip("'")
    _ENV_CACHE = out
    return out


def get_env(name: str, default: str = "") -> str:
    val = os.getenv(name, "").strip()
    if val:
        return val
    return load_local_env().get(name, default).strip()


def get_timeout_seconds(name: str, default: float) -> float:
    raw = get_env(name, str(default))
    try:
        timeout = float(raw)
    except (TypeError, ValueError):
        return float(default)
    if timeout <= 0:
        return float(default)
    return timeout


def log_event(event: str, **fields: Any) -> None:
    ts = datetime.now(timezone.utc).isoformat()
    payload = {"ts": ts, "event": event}
    payload.update(fields)
    logger.info(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
