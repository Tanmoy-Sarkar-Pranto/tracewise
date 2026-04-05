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
