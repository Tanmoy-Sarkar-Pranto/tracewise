from pathlib import Path

_STATIC_ROOT = Path("tracewise/viewer/static")


def _static_text(name: str) -> str:
    return (_STATIC_ROOT / name).read_text(encoding="utf-8")


def test_index_html_defines_split_detail_workspace():
    html = _static_text("index.html")

    assert 'id="detail-workspace"' in html
    assert 'id="trace-tree-panel"' in html
    assert 'id="trace-tree"' in html
    assert 'id="span-detail-panel"' in html
    assert 'id="span-detail"' in html


def test_index_html_uses_sans_first_font_and_responsive_workspace():
    html = _static_text("index.html")

    assert 'font-family: "Avenir Next", "Segoe UI", sans-serif;' in html
    assert "grid-template-columns: minmax(0, 1.35fr) minmax(320px, 0.95fr);" in html
    assert "@media (max-width: 1080px)" in html


def test_app_js_tracks_selected_span_state_and_renders_selected_detail():
    js = _static_text("app.js")

    assert "let activeTraceRoot = null;" in js
    assert "let activeSpanId = null;" in js
    assert "activeSpanId = data.root.span_id;" in js
    assert "renderActiveTrace();" in js
    assert "function findSpanById(span, targetId)" in js
    assert "function renderSelectedSpan(span)" in js


def test_app_js_resets_default_empty_prompt_when_traces_return():
    js = _static_text("app.js")

    assert "function resetEmptyState()" in js
    assert "document.getElementById('detail-empty').textContent = 'Select a trace to inspect it.';" in js
    assert "if (!activeTraceRoot) {" in js
    assert "resetEmptyState();" in js


def test_index_html_wraps_long_attribute_keys_inside_the_label_column():
    html = _static_text("index.html")

    assert ".attr-row { display: grid; grid-template-columns: minmax(0, 140px) minmax(0, 1fr); gap: 10px; }" in html
    assert ".detail-label { color: #8b949e; min-width: 0; overflow-wrap: anywhere; }" in html


def test_index_html_styles_selected_rows_db_badges_and_sql_blocks():
    html = _static_text("index.html")

    assert ".span-row.selected" in html
    assert ".span-row.db" in html
    assert ".db-badge" in html
    assert ".span-preview" in html
    assert ".code-block" in html


def test_app_js_uses_db_metadata_for_tree_rows_and_detail_cards():
    js = _static_text("app.js")

    assert "function isDbSpan(span)" in js
    assert "function getDbOperation(span)" in js
    assert "function getDbStatement(span)" in js
    assert "previewStatement(statement)" in js
    assert "renderDbSpanDetail(span)" in js
    assert "SQL Preview" in js


def test_index_html_uses_mobile_drawer_layout_instead_of_stacked_page_scroll():
    html = _static_text("index.html")

    assert "@media (max-width: 1080px)" in html
    assert "body { height: 100vh; overflow: hidden; }" in html


def test_index_html_defines_mobile_trace_drawer_shell():
    html = _static_text("index.html")

    assert 'id="detail-topbar"' in html
    assert 'id="trace-drawer-toggle"' in html
    assert 'id="current-trace-summary"' in html
    assert 'id="current-trace-name"' in html
    assert 'id="current-trace-meta"' in html
    assert 'id="drawer-backdrop"' in html


def test_index_html_styles_mobile_trace_drawer_overlay_at_current_breakpoint():
    html = _static_text("index.html")

    assert "@media (max-width: 1080px)" in html
    assert "body.drawer-open #sidebar" in html
    assert "transform: translateX(-100%);" in html
    assert "width: min(360px, 82vw);" in html
    assert "#detail-topbar" in html


def test_app_js_tracks_mobile_drawer_state_and_current_trace_summary():
    js = _static_text("app.js")

    assert "let isDrawerOpen = false;" in js
    assert "function isMobileViewport()" in js
    assert "function setDrawerOpen(nextOpen)" in js
    assert "function syncDrawerState()" in js
    assert "function renderCurrentTraceSummary(traceRoot)" in js
    assert "if (isMobileViewport()) { setDrawerOpen(false); }" in js
