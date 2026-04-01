const BASE = window.location.pathname.replace(/\/+$/, '').replace('/index.html', '');
const API = BASE + '/api';

let activeTraceId = null;

async function loadTraces() {
  const resp = await fetch(`${API}/traces?limit=100`);
  const traces = await resp.json();
  const list = document.getElementById('trace-list');
  list.innerHTML = '';

  if (traces.length === 0) {
    list.innerHTML = '<li style="color:#8b949e;padding:16px">No traces yet. Make a request to your app.</li>';
    return;
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
  const detail = document.getElementById('detail');
  detail.innerHTML = `<h2>Trace: ${traceId}</h2>` + renderSpanNode(data.root, true);
}

function renderSpanNode(span, isRoot = false) {
  const duration = span.duration_ms != null ? `${span.duration_ms.toFixed(1)}ms` : '…';
  const statusClass = `status-${span.status}`;
  const attrEntries = Object.entries(span.attributes || {});
  const attrHtml = attrEntries.length
    ? attrEntries.map(([k, v]) => `<div>${escHtml(k)}: <span style="color:#e6edf3">${escHtml(String(v))}</span></div>`).join('')
    : '<div style="color:#6e7681">no attributes</div>';

  const id = `span-${span.span_id}`;
  const childrenHtml = (span.children || []).map(c => renderSpanNode(c)).join('');

  return `
    <div class="span-node">
      <div class="span-row${isRoot ? ' root' : ''}" onclick="toggleAttrs('${id}')">
        <span class="${statusClass}">●</span>
        <span class="span-name">${escHtml(span.name)}</span>
        <span class="span-duration">${duration}</span>
        <span style="color:#6e7681;font-size:11px">${span.kind}</span>
      </div>
      <div class="span-attrs" id="${id}">${attrHtml}</div>
      ${childrenHtml}
    </div>
  `;
}

function toggleAttrs(id) {
  document.getElementById(id).classList.toggle('open');
}

function escHtml(s) {
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

document.getElementById('refresh').onclick = loadTraces;
document.getElementById('clear-btn').onclick = async () => {
  await fetch(`${API}/traces`, { method: 'DELETE' });
  activeTraceId = null;
  document.getElementById('detail').innerHTML = '<div id="empty">Select a trace to inspect it.</div>';
  loadTraces();
};

loadTraces();
