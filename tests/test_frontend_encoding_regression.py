from __future__ import annotations

from pathlib import Path


def test_frontend_static_files_keep_utf8_chinese_text() -> None:
    index_html = Path("frontend/index.html").read_text(encoding="utf-8")
    app_js = Path("frontend/app.js").read_text(encoding="utf-8")

    assert "<meta charset=\"utf-8\">" in index_html
    assert "2026 年宏观市场核心指标看板" in index_html
    assert "全市场 权益/固收/衍生品/外汇/商品等资产 每日监测" in index_html
    assert "战略发展部" not in index_html
    assert "导出为长图" in index_html

    assert "生成日期" in app_js
    assert "异动解释" in index_html
    assert "�" not in index_html
    assert "�" not in app_js
