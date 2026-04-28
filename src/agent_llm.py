from __future__ import annotations

from datetime import datetime, timezone
import json
import time
from typing import Any

import requests

from .agent_evidence import (
    build_driver_evidence,
    normalize_refs,
)
from .agent_prompt import _build_insight_system_prompt
from .agent_runtime import get_env, get_timeout_seconds, log_event
from .agent_tools import MARKET_NEWS_TOOL_SCHEMA, search_market_news


def _truncate_text(text: str, max_len: int) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_len:
        return raw
    return f"{raw[: max_len - 3]}..."


def _extract_json_obj(text: str) -> dict[str, Any] | None:
    raw = text.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        raw = raw.replace("json", "", 1).strip()
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    start = raw.find("{")
    end = raw.rfind("}")
    if start >= 0 and end > start:
        try:
            parsed = json.loads(raw[start : end + 1])
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _default_insight_output(
    context: dict[str, Any], refs: list[dict[str, Any]]
) -> dict[str, Any]:
    asset_fact = context.get("asset_fact") or {}
    asset_name = str(asset_fact.get("asset_name", "")).strip()
    metric_name = str(asset_fact.get("metric_name", "")).strip()
    direction = str(asset_fact.get("direction", "")).strip()
    pct_change = asset_fact.get("pct_change_pct")
    abs_change = asset_fact.get("abs_change")
    unit = str(asset_fact.get("unit", "")).strip()

    if direction == "up":
        direction_text = "上行"
    elif direction == "down":
        direction_text = "下行"
    else:
        direction_text = "方向待确认"

    if pct_change is not None:
        sign = "+" if pct_change >= 0 else ""
        magnitude_text = f"周度变动 {sign}{pct_change:.2f}%，处于历史与横向分位的高位区间。"
    elif abs_change is not None:
        sign = "+" if abs_change >= 0 else ""
        unit_suffix = f" {unit}" if unit and unit.lower() != "raw" else ""
        magnitude_text = f"周度变动 {sign}{abs_change:.4f}{unit_suffix}，处于历史与横向分位的高位区间。"
    else:
        magnitude_text = "变化幅度信息暂缺。"

    driver_evidence = build_driver_evidence(refs, evidence_type="fallback")

    return {
        "direction_summary": f"{asset_name} {metric_name} 本周呈{direction_text}态势。",
        "magnitude_summary": magnitude_text,
        "driver_analysis": "内部数据已显示该指标本周触发异常变动；后续重点观察相关政策、资金面、市场评论与同类资产表现是否同步变化。",
        "driver_note": "fallback",
        "external_references": normalize_refs(refs),
        "driver_evidence": driver_evidence,
        "query_log": [],
    }


def _generate_insight_with_llm(
    context: dict[str, Any],
    allow_external_search: bool = True,
) -> dict[str, Any]:
    api_key = get_env("DEEPSEEK_API_KEY")
    endpoint = get_env("DEEPSEEK_CHAT_ENDPOINT", "https://api.deepseek.com/chat/completions")
    model = get_env("DEEPSEEK_MODEL", "deepseek-chat")
    seed_refs = normalize_refs(context.get("external_evidence_seed", []))
    seed_evidence = build_driver_evidence(seed_refs, evidence_type="seed")
    if not api_key:
        fallback = _default_insight_output(context, seed_refs)
        fallback["external_references"] = seed_refs
        fallback["driver_evidence"] = seed_evidence
        fallback["query_log"] = []
        return fallback

    user_payload = {
        "instruction": (
            "基于以下context生成资产异动洞察。"
            "driver_evidence表示外部背景线索，不是直接因果证据。"
            "driver_analysis应结合内部数据异常与外部市场背景补充解释，不得复述关键词或工具调用痕迹。"
        ),
        "context": context,
    }
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": _build_insight_system_prompt()},
        {"role": "user", "content": json.dumps(user_payload, ensure_ascii=False)},
    ]
    query_log: list[dict[str, Any]] = []
    tool_refs: list[dict[str, Any]] = []
    tool_evidence: list[dict[str, Any]] = []

    tools = [MARKET_NEWS_TOOL_SCHEMA]
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    max_steps = 3 if allow_external_search else 1
    llm_timeout_sec = get_timeout_seconds("DEEPSEEK_HTTP_TIMEOUT_SEC", 120.0)

    try:
        step = 0
        pending_tool_call = False
        asset_name = str(((context.get("asset_fact") or {}).get("asset_name", ""))).strip()
        while step < max_steps:
            step += 1
            log_event("react_step_started", asset_name=asset_name, step=step, max_steps=max_steps)
            payload: dict[str, Any] = {
                "model": model,
                "messages": messages,
                "temperature": 0.2,
                "max_tokens": 1200,
                "response_format": {"type": "json_object"},
            }
            if allow_external_search:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            log_event(
                "llm_request_started",
                asset_name=asset_name,
                step=step,
                timeout_sec=llm_timeout_sec,
                allow_external_search=allow_external_search,
            )
            started_at = time.monotonic()
            try:
                resp = requests.post(endpoint, headers=headers, json=payload, timeout=llm_timeout_sec)
            except requests.Timeout:
                log_event(
                    "llm_request_timeout",
                    asset_name=asset_name,
                    step=step,
                    timeout_sec=llm_timeout_sec,
                    elapsed_sec=round(time.monotonic() - started_at, 3),
                )
                fallback = _default_insight_output(context, seed_refs + tool_refs)
                fallback["driver_note"] = "llm_timeout"
                fallback["external_references"] = normalize_refs(seed_refs + tool_refs)
                fallback["driver_evidence"] = seed_evidence + tool_evidence
                fallback["query_log"] = query_log
                return fallback
            except requests.RequestException as ex:
                log_event(
                    "llm_request_network_error",
                    asset_name=asset_name,
                    step=step,
                    error_type=type(ex).__name__,
                    error_detail=_truncate_text(str(ex), 220),
                    elapsed_sec=round(time.monotonic() - started_at, 3),
                )
                fallback = _default_insight_output(context, seed_refs + tool_refs)
                fallback["driver_note"] = "llm_network_error"
                fallback["external_references"] = normalize_refs(seed_refs + tool_refs)
                fallback["driver_evidence"] = seed_evidence + tool_evidence
                fallback["query_log"] = query_log
                return fallback

            log_event(
                "llm_request_finished",
                asset_name=asset_name,
                step=step,
                status_code=resp.status_code,
                elapsed_sec=round(time.monotonic() - started_at, 3),
            )
            if resp.status_code >= 400:
                fallback = _default_insight_output(context, seed_refs + tool_refs)
                fallback["driver_note"] = f"llm_http_{resp.status_code}"
                fallback["external_references"] = normalize_refs(seed_refs + tool_refs)
                fallback["query_log"] = query_log
                return fallback

            body = resp.json()
            message = body.get("choices", [{}])[0].get("message", {})
            content = str(message.get("content", "") or "")
            tool_calls = message.get("tool_calls", [])

            assistant_msg: dict[str, Any] = {"role": "assistant", "content": content}
            if tool_calls:
                assistant_msg["tool_calls"] = tool_calls
            messages.append(assistant_msg)

            if tool_calls and allow_external_search:
                pending_tool_call = True
                now = datetime.now(timezone.utc).isoformat()
                for tc in tool_calls:
                    fn = (tc.get("function") or {}).get("name", "")
                    call_id = str(tc.get("id", ""))
                    args_raw = (tc.get("function") or {}).get("arguments", "{}")
                    try:
                        args = json.loads(args_raw) if isinstance(args_raw, str) else {}
                    except Exception:
                        args = {}

                    if fn != "search_market_news":
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps({"error": f"unsupported_tool:{fn}"}, ensure_ascii=False),
                            }
                        )
                        continue

                    query = str(args.get("query", "")).strip()
                    recency_days = int(args.get("recency_days", 14))
                    if not query:
                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps({"references": [], "error": "empty_query"}, ensure_ascii=False),
                            }
                        )
                        continue

                    query_log.append(
                        {
                            "generated_query": query,
                            "generated_by": "llm_tool_call",
                            "generation_reason": "insight_generation",
                            "query_time": now,
                        }
                    )
                    log_event(
                        "tool_call_started",
                        asset_name=asset_name,
                        tool_name="search_market_news",
                        query=query,
                        recency_days=recency_days,
                        step=step,
                    )
                    search_result = search_market_news(query=query, recency_days=recency_days)
                    refs = search_result.get("references", [])
                    evidence_items = build_driver_evidence(refs, query=query, evidence_type="tool_search")
                    log_event(
                        "tool_call_finished",
                        asset_name=asset_name,
                        tool_name="search_market_news",
                        status=search_result.get("status", "error"),
                        error_type=search_result.get("error_type", ""),
                        ref_count=len(refs),
                        step=step,
                    )
                    tool_refs.extend(refs)
                    tool_evidence.extend(evidence_items)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": call_id,
                            "content": json.dumps(
                                {
                                    "query": query,
                                    "recency_days": recency_days,
                                    "status": search_result.get("status", "error"),
                                    "error_type": search_result.get("error_type", ""),
                                    "error_message": search_result.get("error_message", ""),
                                    "compact_context": search_result.get("compact_context", ""),
                                    "driver_evidence": evidence_items,
                                    "references": refs,
                                },
                                ensure_ascii=False,
                            ),
                        }
                    )
                continue
            pending_tool_call = False

            parsed = _extract_json_obj(content)
            if isinstance(parsed, dict):
                direction_summary = str(parsed.get("direction_summary", "")).strip()
                magnitude_summary = str(parsed.get("magnitude_summary", "")).strip()
                driver_analysis = str(parsed.get("driver_analysis", "")).strip()
                driver_note = str(parsed.get("driver_note", "")).strip() or "llm_json_output"

                if not direction_summary and not magnitude_summary and not driver_analysis:
                    fallback = _default_insight_output(context, seed_refs + tool_refs)
                    fallback["external_references"] = normalize_refs(seed_refs + tool_refs)
                    fallback["query_log"] = query_log
                    return fallback

                if not driver_analysis:
                    driver_analysis = "内部数据已显示该指标本周触发异常变动；后续重点观察相关政策、资金面、市场评论与同类资产表现是否同步变化。"

                driver_evidence = seed_evidence + tool_evidence

                return {
                    "direction_summary": direction_summary,
                    "magnitude_summary": magnitude_summary,
                    "driver_analysis": driver_analysis,
                    "driver_note": driver_note,
                    "external_references": normalize_refs(seed_refs + tool_refs),
                    "driver_evidence": driver_evidence,
                    "query_log": query_log,
                }

        fallback = _default_insight_output(context, seed_refs + tool_refs)
        if pending_tool_call:
            fallback["driver_analysis"] = "内部数据已显示该指标本周触发异常变动；后续重点观察相关政策、资金面、市场评论与同类资产表现是否同步变化。"
            fallback["direction_summary"] = "当前异常方向已确认，但外部检索未能在限定轮次内完成。"
            fallback["magnitude_summary"] = "历史与横向分位信息已纳入，幅度判断基于内部数据。"
            fallback["driver_note"] = "max_steps_reached_with_tool_calls"
        else:
            fallback["driver_note"] = "llm_round_limit"
        fallback["external_references"] = normalize_refs(seed_refs + tool_refs)
        fallback["driver_evidence"] = seed_evidence + tool_evidence
        fallback["query_log"] = query_log
        return fallback
    except Exception as ex:
        fallback = _default_insight_output(context, seed_refs + tool_refs)
        fallback["driver_note"] = f"llm_exception:{type(ex).__name__}"
        fallback["external_references"] = normalize_refs(seed_refs + tool_refs)
        fallback["driver_evidence"] = seed_evidence + tool_evidence
        fallback["query_log"] = query_log
        return fallback
