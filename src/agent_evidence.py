from __future__ import annotations

from typing import Any


def normalize_refs(refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for ref in refs:
        title = str(ref.get("source_title", "")).strip()
        note = str(ref.get("relevance_note", "")).strip()
        dt = str(ref.get("publish_date", "")).strip()
        key = (title, note, dt)
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "source_title": title,
                "relevance_note": note,
                "publish_date": dt,
                "source_url": str(ref.get("source_url", "")).strip(),
                "retrieved_at": str(ref.get("retrieved_at", "")).strip(),
            }
        )
    return out


def _extract_source_name(url: str) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    host = raw.split("//", 1)[-1].split("/", 1)[0].lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def _looks_like_keyword_note(text: str) -> bool:
    raw = str(text or "").lower()
    markers = [
        "关键词",
        "keyword",
        "market news",
        "macro driver",
        "weekly move",
        "缺乏具体",
        "信息不足",
    ]
    return any(marker in raw for marker in markers)


def _grade_evidence_item(title: str, url: str, publish_date: str, summary: str) -> str:
    has_title = bool(title.strip())
    has_url = bool(url.strip())
    has_date = bool(publish_date.strip())
    has_summary = bool(summary.strip())
    if has_title and has_url and has_date and has_summary and not _looks_like_keyword_note(summary):
        return "confirmed"
    if has_title and has_url and has_summary and not _looks_like_keyword_note(summary):
        return "plausible"
    return "insufficient"


def build_driver_evidence(
    refs: list[dict[str, Any]],
    query: str = "",
    evidence_type: str = "market_news",
) -> list[dict[str, Any]]:
    evidence: list[dict[str, Any]] = []
    for idx, ref in enumerate(normalize_refs(refs), start=1):
        title = str(ref.get("source_title", "")).strip()
        url = str(ref.get("source_url", "")).strip()
        publish_date = str(ref.get("publish_date", "")).strip()
        summary = str(ref.get("relevance_note", "")).strip()
        grade = _grade_evidence_item(title, url, publish_date, summary)
        evidence.append(
            {
                "evidence_id": f"{evidence_type}_{idx}",
                "evidence_type": evidence_type,
                "evidence_grade": grade,
                "title": title,
                "source": _extract_source_name(url) or "unknown",
                "published_at": publish_date,
                "summary": summary,
                "url": url,
                "query": query,
            }
        )
    return evidence


def evidence_confidence(evidence_items: list[dict[str, Any]]) -> str:
    grades = {str(item.get("evidence_grade", "")).lower() for item in evidence_items}
    if "confirmed" in grades:
        return "high"
    if "plausible" in grades:
        return "medium"
    return "low"


_FORBIDDEN_DRIVER_TERMS = (
    "关键词",
    "keyword",
    "market news",
    "macro driver",
    "deepseek",
    "tool_call",
    "search_market_news",
)


def contains_forbidden_driver_terms(text: str) -> bool:
    raw = str(text or "").lower()
    return any(term in raw for term in _FORBIDDEN_DRIVER_TERMS)


def render_evidence_driver_text(evidence_items: list[dict[str, Any]], max_items: int = 2) -> str:
    usable = [x for x in evidence_items if str(x.get("evidence_grade", "")).lower() in {"confirmed", "plausible"}]
    if not usable:
        return "内部数据已显示该指标本周触发异常变动；后续重点观察相关政策、资金面、市场评论与同类资产表现是否同步变化。"
    parts: list[str] = []
    for item in usable[:max_items]:
        dt = str(item.get("published_at", "")).strip() or "日期不明"
        source = str(item.get("source", "")).strip() or "unknown"
        title = str(item.get("title", "")).strip()
        summary = str(item.get("summary", "")).strip()
        seg = f"{dt} {source} 报道《{title}》"
        if summary:
            seg = f"{seg}，核心线索为：{summary}"
        parts.append(seg)
    return f"可能相关的外部背景线索包括：{'；'.join(parts)}。"
