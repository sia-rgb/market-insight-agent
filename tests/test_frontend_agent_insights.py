from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_frontend_has_optional_agent_insights_panel() -> None:
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")
    app_js = (ROOT / "frontend" / "app.js").read_text(encoding="utf-8")

    assert 'id="agentInsightPanel"' in index_html
    assert 'id="agentInsightList"' in index_html
    assert 'fetch("data/agent_insights.json"' in app_js
    assert "renderAgentInsights" in app_js
    assert "labelMetricBrief(item.metric_name)" in app_js
    assert "agentInsights?.as_of_date" in app_js


def test_agent_insights_panel_is_below_toolbar_and_above_global_grid() -> None:
    index_html = (ROOT / "frontend" / "index.html").read_text(encoding="utf-8")

    toolbar_idx = index_html.index('class="toolbar"')
    agent_idx = index_html.index('id="agentInsightPanel"')
    global_grid_idx = index_html.index('class="global-grid"')

    assert toolbar_idx < agent_idx < global_grid_idx
