const BASE = window.location.pathname.replace(/\/+$/, '').replace('/index.html', '');
const API = BASE + '/api';

let activeTraceId = null;
let activeTraceRoot = null;
let activeSpanId = null;

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
    return;
  }

  if (!activeTraceRoot) {
    resetEmptyState();
  }

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
}

function renderActiveTrace() {
  const workspace = document.getElementById('detail-workspace');
  const empty = document.getElementById('detail-empty');
  const tree = document.getElementById('trace-tree');
  const detail = document.getElementById('span-detail');

  if (!activeTraceRoot) {
    workspace.classList.remove('ready');
    empty.style.display = 'flex';
    tree.innerHTML = '';
    detail.innerHTML = '';
    return;
  }

  const activeSpan = findSpanById(activeTraceRoot, activeSpanId) || activeTraceRoot;
  empty.style.display = 'none';
  workspace.classList.add('ready');
  tree.innerHTML = renderTraceTree(activeTraceRoot);
  detail.innerHTML = renderSelectedSpan(activeSpan);
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

function renderSpanNode(span) {
  const duration = span.duration_ms != null ? `${span.duration_ms.toFixed(1)}ms` : '…';
  const statusClass = `status-${span.status}`;
  const selectedClass = span.span_id === activeSpanId ? ' selected' : '';
  const childrenHtml = (span.children || []).map(child => renderSpanNode(child)).join('');

  return `
    <div class="span-node">
      <div class="span-row${selectedClass}" onclick="selectSpan('${span.span_id}')">
        <span class="${statusClass}">●</span>
        <span class="span-name">${escHtml(span.name)}</span>
        <span class="span-duration">${duration}</span>
        <span class="span-kind">${escHtml(span.kind)}</span>
      </div>
      ${childrenHtml ? `<div class="span-children">${childrenHtml}</div>` : ''}
    </div>
  `;
}

function renderSelectedSpan(span) {
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

loadTraces();
