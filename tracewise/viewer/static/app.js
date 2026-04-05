const BASE = window.location.pathname.replace(/\/+$/, '').replace('/index.html', '');
const API = BASE + '/api';

let activeTraceId = null;
let activeTraceRoot = null;
let activeSpanId = null;
let isDrawerOpen = false;

function isMobileViewport() {
  return window.innerWidth <= 1080;
}

function setDrawerOpen(nextOpen) {
  isDrawerOpen = nextOpen;
  syncDrawerState();
}

function syncDrawerState() {
  const expanded = isMobileViewport() && isDrawerOpen;
  document.body.classList.toggle('drawer-open', expanded);
  document.getElementById('trace-drawer-toggle').setAttribute('aria-expanded', String(expanded));
}

function renderCurrentTraceSummary(traceRoot) {
  const nameEl = document.getElementById('current-trace-name');
  const metaEl = document.getElementById('current-trace-meta');

  if (!traceRoot) {
    nameEl.textContent = 'No trace selected';
    metaEl.textContent = 'Choose a trace to inspect it.';
    return;
  }

  const duration = traceRoot.duration_ms != null ? `${traceRoot.duration_ms.toFixed(1)}ms` : '…';
  nameEl.textContent = traceRoot.name;
  metaEl.textContent = `${traceRoot.status} · ${duration}`;
}

function syncResponsiveLayout() {
  if (!isMobileViewport()) {
    isDrawerOpen = false;
  } else if (!activeTraceRoot) {
    isDrawerOpen = true;
  }
  syncDrawerState();
}

async function loadTraces() {
  const resp = await fetch(`${API}/traces?limit=100`);
  const traces = await resp.json();
  const list = document.getElementById('trace-list');
  list.innerHTML = '';

  if (traces.length === 0) {
    activeTraceId = null;
    activeTraceRoot = null;
    activeSpanId = null;
    showEmptyState('No traces yet. Make a request to your app.');
    list.innerHTML = '<li style="color:#8b949e;padding:16px">No traces yet. Make a request to your app.</li>';
    syncResponsiveLayout();
    return;
  }

  if (!activeTraceRoot) {
    resetEmptyState();
  }
  syncResponsiveLayout();

  traces.forEach(trace => {
    const root = trace.root;
    const li = document.createElement('li');
    if (trace.trace_id === activeTraceId) li.classList.add('active');
    const statusClass = `status-${root.status}`;
    const duration = root.duration_ms != null ? `${root.duration_ms.toFixed(1)}ms` : '…';
    li.innerHTML = `
      <div class="trace-name">${escHtml(root.name)}</div>
      <div class="trace-meta">
        <span class="${statusClass}">${root.status}</span>
        &nbsp;·&nbsp;${duration}
        &nbsp;·&nbsp;<span style="opacity:0.6">${root.start_time ? new Date(root.start_time).toLocaleTimeString() : ''}</span>
      </div>
    `;
    li.onclick = () => selectTrace(trace.trace_id, li);
    list.appendChild(li);
  });
}

async function selectTrace(traceId, liEl) {
  activeTraceId = traceId;
  document.querySelectorAll('#trace-list li').forEach(l => l.classList.remove('active'));
  liEl.classList.add('active');

  const resp = await fetch(`${API}/traces/${traceId}`);
  const data = await resp.json();
  activeTraceRoot = data.root;
  activeSpanId = data.root.span_id;
  renderActiveTrace();
  if (isMobileViewport()) { setDrawerOpen(false); }
}

function renderActiveTrace() {
  const workspace = document.getElementById('detail-workspace');
  const empty = document.getElementById('detail-empty');
  const tree = document.getElementById('trace-tree');
  const detail = document.getElementById('span-detail');

  renderCurrentTraceSummary(activeTraceRoot);

  if (!activeTraceRoot) {
    workspace.classList.remove('ready');
    empty.style.display = 'flex';
    tree.innerHTML = '';
    detail.innerHTML = '';
    syncResponsiveLayout();
    return;
  }

  const activeSpan = findSpanById(activeTraceRoot, activeSpanId) || activeTraceRoot;
  empty.style.display = 'none';
  workspace.classList.add('ready');
  tree.innerHTML = renderTraceTree(activeTraceRoot);
  detail.innerHTML = renderSelectedSpan(activeSpan);
  syncResponsiveLayout();
}

function selectSpan(spanId) {
  activeSpanId = spanId;
  renderActiveTrace();
}

function findSpanById(span, targetId) {
  if (!span) return null;
  if (span.span_id === targetId) return span;
  for (const child of span.children || []) {
    const found = findSpanById(child, targetId);
    if (found) return found;
  }
  return null;
}

function renderTraceTree(root) {
  return renderSpanNode(root);
}

function isDbSpan(span) {
  return Boolean(getDbStatement(span) || getDbOperation(span));
}

function getDbOperation(span) {
  return span.attributes && span.attributes["db.operation"] ? String(span.attributes["db.operation"]) : "";
}

function getDbStatement(span) {
  return span.attributes && span.attributes["db.statement"] ? String(span.attributes["db.statement"]) : "";
}

function previewStatement(statement, maxLength = 96) {
  const condensed = statement.replace(/\s+/g, ' ').trim();
  if (condensed.length <= maxLength) return condensed;
  return `${condensed.slice(0, maxLength - 1)}…`;
}

function renderSpanNode(span) {
  const duration = span.duration_ms != null ? `${span.duration_ms.toFixed(1)}ms` : '…';
  const statusClass = `status-${span.status}`;
  const selectedClass = span.span_id === activeSpanId ? ' selected' : '';
  const dbClass = isDbSpan(span) ? ' db' : '';
  const statement = getDbStatement(span);
  const operation = getDbOperation(span);
  const childrenHtml = (span.children || []).map(child => renderSpanNode(child)).join('');
  const previewHtml = statement
    ? `<div class="span-preview">${escHtml(previewStatement(statement))}</div>`
    : '';
  const badgeHtml = isDbSpan(span) ? '<span class="db-badge">DB</span>' : '';
  const operationHtml = operation ? `<span>${escHtml(operation)}</span>` : '';

  return `
    <div class="span-node">
      <div class="span-row${selectedClass}${dbClass}" onclick="selectSpan('${span.span_id}')">
        <span class="${statusClass}">●</span>
        <div class="span-main">
          ${badgeHtml}
          <div class="span-copy">
            <div class="span-name">${escHtml(span.name)}</div>
            ${previewHtml}
          </div>
        </div>
        <div class="span-meta">
          ${operationHtml}
          <span>${escHtml(span.kind)}</span>
          <span>${duration}</span>
        </div>
      </div>
      ${childrenHtml ? `<div class="span-children">${childrenHtml}</div>` : ''}
    </div>
  `;
}

function renderSelectedSpan(span) {
  if (isDbSpan(span)) {
    return renderDbSpanDetail(span);
  }
  return renderGenericSpanDetail(span);
}

function renderGenericSpanDetail(span) {
  return `
    <div class="detail-stack">
      <section class="detail-card">
        <div class="detail-overline">Selected Span</div>
        <div class="detail-title">${escHtml(span.name)}</div>
        <div class="detail-grid">
          ${renderMetadataRows([
            ['Status', span.status],
            ['Kind', span.kind],
            ['Duration', span.duration_ms != null ? `${span.duration_ms.toFixed(1)}ms` : '…'],
            ['Span ID', span.span_id],
            ['Parent', span.parent_span_id || 'root'],
          ])}
        </div>
      </section>
      <section class="detail-card">
        <div class="detail-overline">Attributes</div>
        ${renderRawAttributes(span.attributes || {})}
      </section>
    </div>
  `;
}

function renderDbSpanDetail(span) {
  const statement = getDbStatement(span);
  const operation = getDbOperation(span) || 'DB';
  const system = span.attributes && span.attributes["db.system"] ? String(span.attributes["db.system"]) : 'unknown';
  const title = `
    <div style="display:flex;align-items:center;gap:8px;flex-wrap:wrap">
      <span class="db-badge">DB</span>
      <div class="detail-title" style="margin-bottom:0">${escHtml(span.name)}</div>
    </div>
  `;

  return `
    <div class="detail-stack">
      <section class="detail-card">
        <div class="detail-overline">Selected Span</div>
        ${title}
        <div class="detail-grid" style="margin-top:12px">
          ${renderMetadataRows([
            ['Operation', operation],
            ['System', system],
            ['Status', span.status],
            ['Kind', span.kind],
            ['Duration', span.duration_ms != null ? `${span.duration_ms.toFixed(1)}ms` : '…'],
            ['Parent', span.parent_span_id || 'root'],
          ])}
        </div>
      </section>
      <section class="detail-card detail-section">
        <div class="section-label">SQL Preview</div>
        ${statement
          ? `<pre class="code-block">${escHtml(statement)}</pre>`
          : '<div class="empty-note">No db.statement captured for this span.</div>'}
      </section>
      <section class="detail-card">
        <div class="detail-overline">Raw Attributes</div>
        ${renderRawAttributes(span.attributes || {})}
      </section>
    </div>
  `;
}

function renderMetadataRows(rows) {
  return rows.map(([label, value]) => `
    <div class="detail-label">${escHtml(label)}</div>
    <div class="tech-value">${escHtml(String(value))}</div>
  `).join('');
}

function renderRawAttributes(attributes) {
  const entries = Object.entries(attributes);
  if (entries.length === 0) {
    return '<div class="empty-note">No attributes captured for this span.</div>';
  }

  return `
    <div class="attrs-list">
      ${entries.map(([key, value]) => `
        <div class="attr-row">
          <div class="detail-label">${escHtml(key)}</div>
          <div class="tech-value">${escHtml(String(value))}</div>
        </div>
      `).join('')}
    </div>
  `;
}

function showEmptyState(message) {
  document.getElementById('detail-empty').textContent = message;
  renderActiveTrace();
}

function resetEmptyState() {
  document.getElementById('detail-empty').textContent = 'Select a trace to inspect it.';
  renderActiveTrace();
}

function escHtml(s) {
  return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

document.getElementById('refresh').onclick = loadTraces;
document.getElementById('clear-btn').onclick = async () => {
  await fetch(`${API}/traces`, { method: 'DELETE' });
  activeTraceId = null;
  activeTraceRoot = null;
  activeSpanId = null;
  showEmptyState('Select a trace to inspect it.');
  loadTraces();
};

document.getElementById('trace-drawer-toggle').onclick = () => setDrawerOpen(!isDrawerOpen);
document.getElementById('drawer-backdrop').onclick = () => setDrawerOpen(false);
window.addEventListener('resize', syncResponsiveLayout);
syncResponsiveLayout();
loadTraces();
