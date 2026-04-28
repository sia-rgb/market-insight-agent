from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


_KNOWLEDGE_CACHE: dict[str, str] | None = None


def _truncate_text(text: str, max_len: int) -> str:
    raw = (text or "").strip()
    if len(raw) <= max_len:
        return raw
    return f"{raw[: max_len - 3]}..."


def _read_yaml(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as f:
            loaded = yaml.safe_load(f) or {}
    except Exception:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _format_indicator_dictionary_signal(dictionary_cfg: dict[str, Any], max_chars: int = 2600) -> str:
    indicators = dictionary_cfg.get("indicators", [])
    if not isinstance(indicators, list) or not indicators:
        return "指标词典未读取到有效内容。"

    lines: list[str] = []
    usage = dictionary_cfg.get("usage_policy", {})
    if isinstance(usage, dict):
        fallback = str(usage.get("fallback_when_evidence_insufficient", "")).strip()
        if fallback:
            lines.append(f"证据不足降级语义: {fallback}")

    for item in indicators:
        if not isinstance(item, dict):
            continue
        sheet = str(item.get("sheet", "")).strip()
        metric_name = str(item.get("metric_name", "")).strip()
        semantic = str(item.get("semantic", "")).strip()
        deviation = str(item.get("deviation_meaning", "")).strip()
        linkage = str(item.get("linkage_check", "")).strip()
        if not (sheet and metric_name):
            continue
        lines.append(
            f"{sheet} | {metric_name} | 语义: {semantic} | 偏离含义: {deviation} | 最小联动检查: {linkage}"
        )

    context_items = dictionary_cfg.get("context_indicators", [])
    if isinstance(context_items, list):
        for item in context_items:
            if not isinstance(item, dict):
                continue
            sheet = str(item.get("sheet", "")).strip()
            metric_name = str(item.get("metric_name", "")).strip()
            description = str(item.get("description", "")).strip()
            if sheet and metric_name:
                lines.append(f"上下文指标: {sheet} | {metric_name} | {description}")

    if not lines:
        return "指标词典未读取到有效内容。"
    compact = "\n".join(lines)
    return _truncate_text(compact, max_chars)


def _load_domain_knowledge() -> dict[str, str]:
    global _KNOWLEDGE_CACHE
    if _KNOWLEDGE_CACHE is not None:
        return _KNOWLEDGE_CACHE

    root = Path(".")
    indicator_cfg = _read_yaml(root / "config" / "indicator_dictionary.yaml")
    _KNOWLEDGE_CACHE = {
        "indicator_dictionary": _format_indicator_dictionary_signal(indicator_cfg, max_chars=2600),
    }
    return _KNOWLEDGE_CACHE


def _build_insight_system_prompt() -> str:
    knowledge = _load_domain_knowledge()
    indicator_knowledge = knowledge.get("indicator_dictionary", "《指标词典》缺失。")
    return (
        "你是资产监控系统的智能体判断层（Workflow B）。"
        "你将收到一个JSON Context，里面包含已验证的数值事实与可用外部背景线索。"
        "你的任务是围绕‘变化方向、变化幅度、数据驱动力分析’三个要点生成审慎的异动洞察，必须严格区分事实与推断。"
        "输出必须是JSON对象，不得输出Markdown。"
        "输出字段要求："
        'direction_summary(string, 用1-2句话说明本周变化方向，如上行/下行/震荡及其简要判断依据),'
        'magnitude_summary(string, 用1-2句话说明变化幅度在历史与同类资产中的位置),'
        'driver_analysis(string, 先基于内部数据说明异常本身，再结合外部检索得到的相关新闻报道、分析师观点、市场评论、政策/资金面/行业相关因素补充背景解释；外部信息只能作为背景线索或可能相关因素，不得表述为直接因果证据),'
        "driver_note(string)。"
        "硬约束："
        "1) 不得篡改输入中的数值事实；"
        "2) 驱动描述必须使用审慎措辞（如‘可能’‘或与...有关’），禁止确定性因果断言；"
        "3) 优先输出分析师口吻的完整中文句子，避免模板化短语；"
        "4) driver_analysis禁止使用‘暂难确认具体驱动力’、‘具体驱动力尚不明确’等空泛收尾，"
        "证据不足时说明仍需继续观察的数据或事件线索；"
        "5) 不得写‘暂无外部驱动证据’、‘缺乏直接驱动因素证据’、‘未检索到直接关联的外部证据’。"
        "外部搜索目标是补充市场背景信息，不要求证明直接因果；"
        "6) 如调用搜索工具，检索词应围绕输入中的资产、指标、资产类别与时间窗口，覆盖相关新闻报道、分析师分析、市场评论、政策/资金面/行业相关因素。"
        "\n\n《指标词典》摘要（config/indicator_dictionary.yaml）:\n"
        f"{indicator_knowledge}"
    )
