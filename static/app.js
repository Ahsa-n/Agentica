/* =====================================================================
   AGENTICA console — client
   The agent loop runs on the server (agent.py, LangGraph). This page sends
   messages, approvals and cancels, and renders the events the server
   streams back over /api/sessions/{id}/events.
   ---------------------------------------------------------------------
   - Auto mode / task cards, tool scoping and approvals are decided on the
     server; this file only sends the selected mode and renders results.
   - Telemetry arrives over Server-Sent Events, once per second.
   ===================================================================== */

const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
function el(tag, cls, html) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (html != null) n.innerHTML = html;
  return n;
}
const store = {
  get(k, d) { try { const v = localStorage.getItem(k); return v == null ? d : JSON.parse(v); } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* storage unavailable */ } },
};

/* ---------------- static config ---------------- */

const ICON = {
  auto: '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M5.6 5.6l2.1 2.1M16.3 16.3l2.1 2.1M5.6 18.4l2.1-2.1M16.3 7.7l2.1-2.1"/>',
  monitor: '<path d="M3 12h4l3-8 4 16 3-8h4"/>',
  storage: '<ellipse cx="12" cy="6" rx="8" ry="3"/><path d="M4 6v12c0 1.7 3.6 3 8 3s8-1.3 8-3V6M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
  services: '<path d="M12 3v8"/><path d="M6.3 6.6a8 8 0 1 0 11.4 0"/>',
  network: '<path d="M2.5 9a14 14 0 0 1 19 0M5.5 12.5a9.5 9.5 0 0 1 13 0M8.6 16a5 5 0 0 1 6.8 0"/><circle cx="12" cy="19.3" r=".6"/>',
  apps: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M3 9h18M7 6.5h.01M10 6.5h.01"/>',
  troubleshoot: '<path d="M14.7 6.3a4 4 0 0 0-5.3 5.3L3.5 17.5l3 3 5.9-5.9a4 4 0 0 0 5.3-5.3l-2.6 2.6-2.3-.7-.7-2.3z"/>',
  tool: '<path d="m4 17 6-6-6-6M12 19h8"/>',
  route: '<path d="M5 4v8a4 4 0 0 0 4 4h10M15 12l4 4-4 4"/>',
  copy: '<rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"/>',
  chev: '<path d="m6 9 6 6 6-6"/>',
};
const svg = (name, cls = '') => `<svg class="${cls}" viewBox="0 0 24 24" aria-hidden="true">${ICON[name]}</svg>`;

const suggestions = () => {
  const win = !state.host || /windows/i.test(state.host.os);
  return [
    { tag: 'AUTO', mode: 'auto', text: 'What is using the most memory on this machine right now?' },
    { tag: 'TROUBLESHOOT', mode: 'troubleshoot', text: 'This machine feels slow. Find out why.' },
    { tag: 'SERVICES', mode: 'services', text: win ? 'Are any automatic services stopped that should be running?' : 'Are any services in a failed state?' },
    { tag: 'AUTO', mode: 'auto', text: 'What does a DNS cache flush do, and when should I use one?' },
  ];
};

/* ---------------- state ---------------- */

const state = {
  models: [],
  model: store.get('agentica.model', null),
  think: store.get('agentica.think', true),
  mode: 'auto',
  toolsets: [],
  tools: [],
  host: null,
  telemetry: null,
  monitorOpen: store.get('agentica.monitor', false),
  machines: [],                  // registered remote machines
  localHost: null,               // this PC's hostname
  defaultTarget: store.get('agentica.target', null),   // target for new sessions (null = this PC)
  sessions: [],                  // from the server (GET /api/sessions)
  current: null,                 // {id, title, target, state}
  busy: false,
  lastTps: null,
};
const toolset = (id) => state.toolsets.find((t) => t.id === id) || null;
const loadable = () => state.toolsets.filter((t) => !t.card_only);
const modelInfo = (name = state.model) => state.models.find((m) => m.name === name);
const caps = (name = state.model) => modelInfo(name)?.capabilities || [];

/* ---------------- formatting ---------------- */

const pad = (n) => String(n).padStart(2, '0');
const clock = (t) => { const d = new Date(t); return `${pad(d.getHours())}:${pad(d.getMinutes())}`; };
const secs = (ms) => (ms < 10000 ? (ms / 1000).toFixed(1) : Math.round(ms / 1000)) + 's';
const gb = (b) => (b / 1024 ** 3).toFixed(b >= 100 * 1024 ** 3 ? 0 : 1);
const level = (p) => (p >= 90 ? 'hot' : p >= 70 ? 'warn' : '');
function rate(bps) {
  const bits = bps * 8;
  if (bits >= 1e6) return (bits / 1e6).toFixed(1) + ' Mb/s';
  if (bits >= 1e3) return Math.round(bits / 1e3) + ' kb/s';
  return Math.round(bits) + ' b/s';
}
function uptime(s) {
  const d = Math.floor(s / 86400), h = Math.floor((s % 86400) / 3600), m = Math.floor((s % 3600) / 60);
  return d ? `up ${d}d ${h}h` : `up ${h}h ${m}m`;
}

/* ---------------- markdown (escape-first) ---------------- */

function inline(s) {
  const codes = [];
  s = s.replace(/`([^`\n]+)`/g, (_, c) => { codes.push(c); return `\u0001${codes.length - 1}\u0001`; });
  s = esc(s)
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*\w])\*([^*\n]+)\*(?!\w)/g, '$1<em>$2</em>')
    .replace(/(^|[^_\w])_([^_\n]+)_(?!\w)/g, '$1<em>$2</em>')
    .replace(/~~([^~\n]+)~~/g, '<del>$1</del>')
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
  return s.replace(/\u0001(\d+)\u0001/g, (_, i) => `<code>${esc(codes[+i])}</code>`);
}

function md(src) {
  const blocks = [];
  src = src.replace(/```([\w+-]*)[^\n]*\n([\s\S]*?)(?:```|$)/g, (_, lang, code) => {
    blocks.push({ lang, code: code.replace(/\n$/, '') });
    return `\n\u0000${blocks.length - 1}\u0000\n`;
  });
  const lines = src.split('\n');
  const out = [];
  let para = [];
  const flush = () => { if (para.length) { out.push(`<p>${para.map(inline).join('<br>')}</p>`); para = []; } };
  const cells = (l) => l.trim().replace(/^\||\|$/g, '').split('|').map((c) => c.trim());

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    let m;
    if ((m = line.match(/^\u0000(\d+)\u0000$/))) {
      flush();
      const b = blocks[+m[1]];
      out.push(`<div class="codeblock"><div class="code-head"><span>${esc(b.lang || 'text')}</span><button class="code-copy" type="button">Copy</button></div><pre><code>${esc(b.code)}</code></pre></div>`);
    } else if (!line.trim()) {
      flush();
    } else if ((m = line.match(/^(#{1,6})\s+(.*)$/))) {
      flush();
      const lv = Math.min(m[1].length + 1, 4);
      out.push(`<h${lv}>${inline(m[2])}</h${lv}>`);
    } else if (/^\s*([-*_])\s*\1\s*\1[\s\-*_]*$/.test(line)) {
      flush(); out.push('<hr>');
    } else if (line.includes('|') && i + 1 < lines.length && /^\s*\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)*\|?\s*$/.test(lines[i + 1])) {
      flush();
      const head = cells(line);
      const rows = [];
      i += 2;
      while (i < lines.length && lines[i].includes('|') && lines[i].trim()) { rows.push(cells(lines[i])); i++; }
      i--;
      out.push(`<div class="table-wrap"><table><thead><tr>${head.map((h) => `<th>${inline(h)}</th>`).join('')}</tr></thead><tbody>${rows.map((r) => `<tr>${head.map((_, j) => `<td>${inline(r[j] ?? '')}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`);
    } else if (/^\s*[-*+]\s+/.test(line) || /^\s*\d+[.)]\s+/.test(line)) {
      flush();
      const ordered = /^\s*\d+[.)]\s+/.test(line);
      const re = ordered ? /^\s*\d+[.)]\s+/ : /^\s*[-*+]\s+/;
      const items = [];
      while (i < lines.length && (re.test(lines[i]) || (/^\s{2,}\S/.test(lines[i]) && items.length))) {
        if (re.test(lines[i])) items.push(lines[i].replace(re, ''));
        else items[items.length - 1] += ' ' + lines[i].trim();
        i++;
      }
      i--;
      const tag = ordered ? 'ol' : 'ul';
      out.push(`<${tag}>${items.map((t) => `<li>${inline(t)}</li>`).join('')}</${tag}>`);
    } else if (/^>\s?/.test(line)) {
      flush();
      const q = [];
      while (i < lines.length && /^>\s?/.test(lines[i])) { q.push(lines[i].replace(/^>\s?/, '')); i++; }
      i--;
      out.push(`<blockquote>${q.map(inline).join('<br>')}</blockquote>`);
    } else {
      para.push(line);
    }
  }
  flush();
  return out.join('');
}

function jsonHL(obj) {
  return esc(JSON.stringify(obj, null, 2)).replace(
    /(&quot;(?:\\&quot;|\\\\|[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/g,
    (m, str, colon, kw) => {
      if (str) return colon ? `<span class="j-k">${str}</span>${colon}` : `<span class="j-s">${str}</span>`;
      if (kw) return `<span class="j-b">${m}</span>`;
      return `<span class="j-n">${m}</span>`;
    },
  );
}

/* ---------------- scrolling ---------------- */

const scroller = $('#scroller');
const nearBottom = () => scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight < 140;
function follow(fn) {
  const stick = nearBottom();
  fn();
  if (stick) scroller.scrollTop = scroller.scrollHeight;
}

/* ---------------- transcript elements ---------------- */

const logEl = $('#log');
const hero = $('#hero');

function renderUser(item) {
  const m = el('div', 'msg msg-user');
  if (item.id) m.dataset.id = item.id;
  const b = el('div', 'bubble');
  const ts = toolset(item.scope);
  const tags = [];
  if (ts) tags.push(`${esc(ts.name)} card`);
  const tg = item.targets || (item.target ? [item.target] : []);
  if (tg.length) tags.push(`<span class="to">→ ${tg.map((t) => esc(t === LOCAL ? 'This PC' : t)).join(', ')}</span>`);
  if (tags.length) b.append(el('div', 'scope-tag', tags.join(' · ')));
  b.append(document.createTextNode(item.text));
  m.append(b);
  follow(() => logEl.append(m));
}

function agentShell(item) {
  const m = el('div', 'msg msg-agent');
  m.innerHTML = `<div class="who"><span class="who-mark">A</span>Agentica<time>${clock(item.t)}</time></div>`;
  const body = el('div', 'agent-body');
  m.append(body);
  return { m, body };
}

function stepToggle(root) {
  root.querySelector('.step-row').onclick = () => {
    root.classList.toggle('open');
    root.querySelector('.step-row').setAttribute('aria-expanded', root.classList.contains('open'));
  };
}

function traceEl(seg, live) {
  const root = el('div', 'step trace' + (live ? ' live open' : ''));
  root.innerHTML = `<button class="step-row" type="button" aria-expanded="${live}"><span class="glyph"></span><span class="lbl"></span>${svg('chev', 'chev')}</button><div class="step-body"></div>`;
  const body = root.querySelector('.step-body');
  const lbl = root.querySelector('.lbl');
  body.textContent = seg.text;
  stepToggle(root);
  const setLabel = () => { lbl.textContent = seg.done || !live ? `Thought for ${secs(seg.ms || 0)}` : `Thinking… ${secs(seg.ms || 0)}`; };
  setLabel();
  return { root, body, setLabel, close() { root.classList.remove('live', 'open'); } };
}

const APPROVAL_DONE = {
  approved: ['ok', (a) => `✓ Approved by operator${a.decided ? ` at ${clock(a.decided)}` : ''}`],
  failed: ['warn', () => '✓ Approved, but the action failed (see result)'],
  declined: ['no', () => '✕ Declined by operator'],
  refused: ['no', () => '✕ Refused when re-checked against the policy'],
  expired: ['no', () => '⏱ The approval request expired'],
};
const CHIP_BY_STATE = { approved: 'APPROVED', failed: 'FAILED', declined: 'DECLINED', refused: 'DENY', expired: 'EXPIRED' };

function approvalPanel(seg) {
  const a = seg.approval;
  if (!a) return '';
  if (a.state === 'pending') {
    return `<div class="approval" role="group" aria-label="Approval required">
      <div class="ap-head"><span class="ap-title">Approval required</span><span class="chip confirm">${esc(a.risk)} · ${esc(a.risk_label || '')}</span><span class="ap-exp"></span></div>
      <div class="ap-sum">${esc(a.summary)}</div>
      ${a.reasons?.length ? `<ul class="ap-reasons">${a.reasons.map((r) => `<li>${esc(r)}</li>`).join('')}</ul>` : ''}
      <div class="ap-actions"><button type="button" class="btn primary ap-approve">Approve</button><button type="button" class="btn ghost ap-deny">Deny</button></div>
    </div>`;
  }
  const [cls, text] = APPROVAL_DONE[a.state] || ['no', () => a.state];
  return `<div class="ap-done ${cls}">${esc(text(a))}</div>`;
}

function toolEl(seg) {
  const root = el('div', 'step tool');
  const args = Object.entries(seg.args || {}).map(([k, v]) => `${esc(k)}=${esc(JSON.stringify(v))}`).join(', ');
  root.innerHTML = `<button class="step-row" type="button" aria-expanded="false">${svg('tool', 'ico')}<span class="sig"><b>${esc(seg.name)}</b>(${args})</span><span class="chip host" hidden></span>${seg.auto ? '<span class="chip auto">AUTO</span>' : ''}<span class="chip wait">…</span><span class="ms"></span>${svg('chev', 'chev')}</button><div class="ap-slot"></div><div class="step-body"></div>`;
  const chip = root.querySelector('.chip.wait');
  const ms = root.querySelector('.ms');
  const slot = root.querySelector('.ap-slot');
  const body = root.querySelector('.step-body');
  stepToggle(root);
  const hostChip = root.querySelector('.chip.host');
  const update = () => {
    const where = seg.res?.target;
    hostChip.hidden = !where || where.toLowerCase() === (state.localHost || '').toLowerCase();
    if (!hostChip.hidden) hostChip.textContent = `@ ${where}`;
    root.classList.toggle('failed', seg.status === 'failed');
    root.classList.toggle('pending', seg.status === 'pending');
    slot.innerHTML = approvalPanel(seg);
    if (seg.status === 'running') { ms.innerHTML = '<span class="scan"></span>'; return; }
    if (seg.status === 'pending') { chip.className = 'chip confirm'; chip.textContent = 'CONFIRM'; ms.textContent = ''; return; }
    const r = seg.res || {};
    const ok = r.decision === 'ALLOW' && !r.error;
    const unverified = ok && r.result?.verified === false;
    chip.className = 'chip ' + (unverified ? 'confirm' : ok ? 'allow' : 'deny');
    chip.textContent = unverified ? 'UNVERIFIED' : (seg.approval ? CHIP_BY_STATE[seg.approval.state] : null) || r.decision || 'ERROR';
    ms.textContent = r.elapsed_ms != null ? `${r.elapsed_ms}ms` : '';
    body.innerHTML = (r.result ? `<pre>${jsonHL(r.result)}</pre>` : '') + (r.error ? `<div class="err">${esc(r.error)}</div>` : '');
    if (!ok && !seg.approval) root.classList.add('open');
  };
  update();
  return { root, update, slot };
}

const tsName = (d) => toolset(d)?.name || d;
function routeEl(seg) {
  if (seg.via !== 'router') {             // stage 2 fallback: the model asked for more tools itself
    const names = seg.domains.map(tsName).join(', ');
    return el('div', 'route', seg.error
      ? `${svg('route')}<span>load_tools — ${esc(seg.error)}</span>`
      : `${svg('route')}<span>Model loaded <b>${esc(names)}</b> tools · ${esc(seg.tools.join(', '))}</span>`);
  }
  if (seg.error) return el('div', 'route', `${svg('route')}<span>Router · ${esc(seg.error)}</span>`);
  const kept = (seg.kept || []).filter((d) => !seg.domains.includes(d));
  const scores = Object.entries(seg.scores || {}).sort((a, b) => b[1] - a[1]);
  const n = el('div', 'route');
  n.title = 'Stage 1 router (embedding similarity)\n' + scores.map(([c, v]) => `${c === 'none' ? 'no tools' : tsName(c)}: ${v.toFixed(2)}`).join('\n')
    + (seg.context ? '\nShort follow-up: routed together with the previous request' : '');
  const tail = `<span class="rt-ms">${seg.ms} ms</span>`;
  if (!seg.domains.length) {
    n.innerHTML = `${svg('route')}<span>Router · no tools needed${kept.length ? ` · ${esc(kept.map(tsName).join(', '))} still loaded` : ''}</span>${tail}`;
    return n;
  }
  const names = seg.domains.map((d) => `<b>${esc(tsName(d))}</b>${seg.new && !seg.new.includes(d) ? ' (already loaded)' : ''}`).join(', ');
  n.innerHTML = `${svg('route')}<span>Routed to ${names} · ${esc(seg.tools.join(', '))}${seg.context ? ' · from context' : ''}</span>${tail}`;
  return n;
}
const noticeEl = (seg) => el('div', 'notice', esc(seg.text));
const proseEl = (seg, live) => { const n = el('div', 'prose' + (live ? ' caret' : '')); n.innerHTML = md(seg.text); return n; };

function metaEl(item) {
  const s = item.stats;
  const n = el('div', 'meta');
  if (!s) return n;
  const parts = [];
  if (item.evidence > 0) parts.push(`<span class="grounded">✓ grounded · ${item.evidence} tool result${item.evidence > 1 ? 's' : ''}</span>`);
  else if (item.decided > 0) parts.push('<span class="grounded">✓ based on a definitive tool response</span>');
  else if (item.scope) parts.push('<span class="ungrounded">⚠ not verified by a tool</span>');
  parts.push(`<span>${secs(s.ms)}</span>`);
  if (s.tps) parts.push(`<span>${s.tps.toFixed(1)} tok/s</span>`);
  parts.push(`<span>${esc(s.model)}${s.think ? ' · think' : ''}</span>`);
  n.innerHTML = parts.join('') + `<button class="copy" type="button" title="Copy answer" aria-label="Copy answer">${svg('copy')}</button>`;
  n.querySelector('.copy').onclick = () => {
    const text = item.segments.filter((x) => x.kind === 'text').map((x) => x.text).join('\n\n');
    navigator.clipboard?.writeText(text);
  };
  return n;
}

const SEG_RENDER = {
  thinking: (s) => traceEl(s, false).root,
  tool: (s) => toolEl(s).root,
  route: routeEl,
  notice: noticeEl,
  text: (s) => proseEl(s, false),
};

function agentStaticEl(item) {
  const { m, body } = agentShell(item);
  if (item.id) m.dataset.id = item.id;
  for (const seg of item.segments) { const f = SEG_RENDER[seg.kind]; if (f) body.append(f(seg)); }
  if (item.error) body.append(el('div', 'alert', `<b>Error</b> · ${esc(item.error)}`));
  if (item.interrupted) body.append(el('div', 'meta', 'stopped'));
  if (item.stats) body.append(metaEl(item));
  return m;
}
function renderAgentStatic(item) { logEl.append(agentStaticEl(item)); }

/* ---------------- live view: renders events streamed by the server-side agent ---------------- */

const LOCAL = 'local';
const toolsIn = (ids) => state.tools.filter((t) => t.toolsets.some((s) => ids.includes(s)));
function setAttention(on) { document.title = on ? '● Approval needed · Agentica' : 'Agentica Console'; }

class LiveView {
  constructor(item) {
    this.item = { ...item, segments: [] };
    const { m, body } = agentShell(item);
    this.m = m;
    this.body = body;
    this.nodes = [];
    this.pendingRender = new Set();
    this.work = el('div', 'working', '<span class="scan"></span><span></span>');
    this.timer = setInterval(() => this.tick(), 200);
    (item.segments || []).forEach((seg, i) => this.mount(i, seg));
    follow(() => logEl.append(m));
  }
  add(node) {
    follow(() => (this.work.parentNode === this.body ? this.body.insertBefore(node, this.work) : this.body.append(node)));
  }
  status(text) {
    if (!text) { this.work.remove(); return; }
    this.work.lastChild.textContent = text;
    follow(() => this.body.append(this.work));
  }
  mount(i, data) {
    const seg = structuredClone(data);
    this.item.segments[i] = seg;
    let v;
    if (seg.kind === 'thinking') { v = traceEl(seg, !seg.done); v.t0 = performance.now() - (seg.ms || 0); }
    else if (seg.kind === 'text') v = { root: proseEl(seg, true) };
    else if (seg.kind === 'tool') v = toolEl(seg);
    else { const f = SEG_RENDER[seg.kind]; v = { root: f ? f(seg) : el('div') }; }
    this.nodes[i] = v;
    this.add(v.root);
    if (seg.kind === 'tool') this.wireApproval(seg, v);
  }
  delta(i, text) {
    const seg = this.item.segments[i], v = this.nodes[i];
    if (!seg || !v) return;
    seg.text += text;
    if (seg.kind === 'thinking') {
      follow(() => { v.body.append(text); v.body.scrollTop = 1e9; });
    } else if (seg.kind === 'text' && !this.pendingRender.has(i)) {
      this.pendingRender.add(i);
      requestAnimationFrame(() => { this.pendingRender.delete(i); follow(() => { v.root.innerHTML = md(seg.text); }); });
    }
  }
  set(i, data) {
    const seg = this.item.segments[i], v = this.nodes[i];
    if (!seg || !v) { this.mount(i, data); return; }
    for (const k of Object.keys(seg)) if (!(k in data)) delete seg[k];
    Object.assign(seg, structuredClone(data));            // same object the element closes over
    if (seg.kind === 'thinking') { v.setLabel(); if (seg.done) v.close(); }
    else if (seg.kind === 'text') { v.root.classList.remove('caret'); follow(() => { v.root.innerHTML = md(seg.text); }); }
    else if (seg.kind === 'tool') { follow(() => v.update()); this.wireApproval(seg, v); }
  }
  tick() {
    this.item.segments.forEach((seg, i) => {
      if (seg?.kind === 'thinking' && !seg.done && this.nodes[i]) { seg.ms = performance.now() - this.nodes[i].t0; this.nodes[i].setLabel(); }
    });
  }
  /** Approval card buttons -> POST to the session; the outcome arrives as events. */
  wireApproval(seg, v) {
    if (seg.status !== 'pending' || seg.approval?.state !== 'pending') return;
    const panel = v.slot.querySelector('.approval');
    if (!panel || panel.dataset.wired) return;
    panel.dataset.wired = '1';
    setAttention(true);
    const exp = panel.querySelector('.ap-exp');
    const tick = () => {
      if (!panel.isConnected) { clearInterval(t); return; }
      const left = (seg.approval.expires || 0) * 1000 - Date.now();
      exp.textContent = left > 0 ? `expires in ${Math.floor(left / 60000)}:${pad(Math.floor(left / 1000) % 60)}` : 'expired';
    };
    const t = setInterval(tick, 1000);
    tick();
    const decide = async (action) => {
      panel.querySelectorAll('button').forEach((b) => (b.disabled = true));
      if (action === 'approve') panel.querySelector('.ap-approve').textContent = 'Running…';
      try {
        const r = await fetch(`/api/sessions/${state.current.id}/approval`, {
          method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ action }) });
        if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
        setAttention(false);
      } catch (err) {
        panel.querySelectorAll('button').forEach((b) => (b.disabled = false));
        panel.querySelector('.ap-approve').textContent = 'Approve';
        exp.textContent = err.message;
      }
    };
    panel.querySelector('.ap-approve').onclick = () => decide('approve');
    panel.querySelector('.ap-deny').onclick = () => decide('deny');
    panel.querySelector('.ap-approve').focus({ preventScroll: true });
  }
  finish(item) {
    clearInterval(this.timer);
    setAttention(false);
    follow(() => this.m.replaceWith(agentStaticEl(item)));
  }
  dispose() { clearInterval(this.timer); }
}

/* ---------------- session stream (SSE) ---------------- */

let sessionStream = null;
let live = null;

function closeStream() { sessionStream?.close(); sessionStream = null; live?.dispose(); live = null; }

function openStream(sid) {
  closeStream();
  sessionStream = new EventSource(`/api/sessions/${sid}/events`);
  sessionStream.onmessage = (e) => onSessionEvent(sid, JSON.parse(e.data));
}

function applySession(s) {
  if (!s || !state.current || s.id !== state.current.id) return;
  Object.assign(state.current, s);
  $('#title').textContent = s.title || 'New session';
  setBusy(s.state === 'running' || s.state === 'paused');
  renderTargetSelect();
}

function renderSnapshot(snap) {
  live?.dispose();
  live = null;
  clearLog();
  hero.hidden = !(snap.items.length || snap.live);
  for (const it of snap.items) it.type === 'user' ? renderUser(it) : renderAgentStatic(it);
  if (snap.live) {
    live = new LiveView(snap.live);
    live.status(snap.status);
  }
  applySession(snap.session);
  scroller.scrollTop = scroller.scrollHeight;
}

function onSessionEvent(sid, ev) {
  if (!state.current || state.current.id !== sid) return;
  switch (ev.type) {
    case 'snapshot': renderSnapshot(ev); break;
    case 'user':
      hero.hidden = true;
      if (!logEl.querySelector(`[data-id="${ev.item.id}"]`)) renderUser(ev.item);
      break;
    case 'item_start': live?.dispose(); live = new LiveView(ev.item); setBusy(true); break;
    case 'seg_add': live?.mount(ev.i, ev.seg); break;
    case 'seg_delta': live?.delta(ev.i, ev.text); break;
    case 'seg_set': live?.set(ev.i, ev.seg); break;
    case 'status': live?.status(ev.text); break;
    case 'paused': applySession(ev.session); break;
    case 'session': applySession(ev.session); break;
    case 'turn_end':
      if (live) live.finish(ev.item); else renderAgentStatic(ev.item);
      live = null;
      if (ev.item?.stats?.tps) state.lastTps = ev.item.stats.tps;
      applySession(ev.session);
      renderModelTile();
      loadSessions();
      break;
  }
}

async function send(text) {
  text = text.trim();
  if (state.busy || !text) return;
  setBusy(true);
  try {
    if (!state.model) await loadModels();          // the page may still be loading the model list
    if (!state.model) throw new Error('No model available. Is Ollama running?');
    if (!state.current) {
      const r = await fetch('/api/sessions', { method: 'POST', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target: state.defaultTarget }) });
      state.current = await r.json();
      hero.hidden = true;
      openStream(state.current.id);
    }
    const r = await fetch(`/api/sessions/${state.current.id}/messages`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ text, mode: state.mode, think: state.think, model: state.model }) });
    if (!r.ok) throw new Error((await r.json()).detail || `HTTP ${r.status}`);
    loadSessions();
  } catch (err) {
    setBusy(false);
    follow(() => logEl.append(el('div', 'alert', `<b>Error</b> · ${esc(err.message)}`)));
  }
}

async function cancelRun() {
  if (state.current) await fetch(`/api/sessions/${state.current.id}/cancel`, { method: 'POST' }).catch(() => {});
}

/* ---------------- composer ---------------- */

const input = $('#input');
const btnSend = $('#btnSend');
const btnThink = $('#btnThink');

function setBusy(on) {
  state.busy = on;
  btnSend.classList.toggle('stop', on);
  btnSend.setAttribute('aria-label', on ? 'Stop' : 'Send');
  updateSend();
}
const updateSend = () => { btnSend.disabled = !state.busy && (!input.value.trim() || !state.model); };
const autosize = () => { input.style.height = 'auto'; input.style.height = Math.min(input.scrollHeight, 200) + 'px'; };

$('#composer').addEventListener('submit', (e) => {
  e.preventDefault();
  if (state.busy) { cancelRun(); return; }
  const text = input.value;
  if (!text.trim()) return;
  input.value = '';
  autosize(); updateSend();
  send(text);
});
input.addEventListener('input', () => { autosize(); updateSend(); });
input.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing) { e.preventDefault(); if (!state.busy) $('#composer').requestSubmit(); }
});

function renderThink() {
  const ok = !state.model || caps().includes('thinking');
  btnThink.disabled = !ok;
  btnThink.setAttribute('aria-checked', String(ok && state.think));
  btnThink.title = ok ? 'Reasoning on/off (Alt+T)' : 'This model does not support thinking';
}
btnThink.onclick = () => { state.think = !state.think; store.set('agentica.think', state.think); renderThink(); };

/* modes (task cards) */
function renderModes() {
  const wrap = $('#modes');
  wrap.innerHTML = '';
  const items = [{ id: 'auto', name: 'Auto', desc: 'the router loads only the tools a request needs' }, ...state.toolsets];
  for (const t of items) {
    const b = el('button', 'mode', `${svg(ICON[t.id] ? t.id : 'tool')}${esc(t.name)}`);
    b.type = 'button';
    b.setAttribute('role', 'radio');
    b.setAttribute('aria-checked', String(state.mode === t.id));
    b.title = t.id === 'auto' ? 'Auto: no tools until the model decides it needs them' : `${t.name}: ${t.desc} · ${t.tools.length} tools · tool call required`;
    b.onclick = () => setMode(t.id);
    wrap.append(b);
  }
}
function setMode(id) {
  state.mode = id;
  renderModes();
  renderHint();
}
function renderHint() {
  const hint = $('#modeHint');
  if (state.model && !caps().includes('tools')) { hint.textContent = 'this model can’t call tools'; return; }
  const card = toolset(state.mode);
  const changes = card && toolsIn([card.id]).some((t) => t.risk !== 'R0');
  hint.textContent = card
    ? `${card.name} · ${card.tools.length} tool${card.tools.length > 1 ? 's' : ''} · evidence required${changes ? ' · changes need approval' : ''}`
    : 'Auto · the router picks the tools';
}

/* ---------------- sessions ---------------- */

async function loadSessions() {
  try {
    const r = await fetch('/api/sessions');
    if (r.ok) state.sessions = (await r.json()).sessions;
  } catch { /* offline */ }
  renderSessions();
}

function renderSessions() {
  const ul = $('#sessionList');
  ul.innerHTML = '';
  if (!state.sessions.length) { ul.append(el('li', 'empty', 'No sessions yet')); return; }
  for (const s of state.sessions) {
    const li = el('li', s.id === state.current?.id ? 'on' : '');
    const badge = s.state === 'paused' ? ' <span class="led led-warn" title="Waiting for approval"></span>'
      : s.state === 'running' ? ' <span class="led led-ok pulse" title="Working"></span>' : '';
    li.innerHTML = `<span class="s-title">${esc(s.title || 'Untitled')}</span>${badge}<button class="s-del" type="button" aria-label="Delete session"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`;
    li.title = s.title || '';
    li.onclick = () => { openSession(s.id); closeDrawer(); };
    li.querySelector('.s-del').onclick = async (e) => {
      e.stopPropagation();
      const r = await fetch(`/api/sessions/${s.id}`, { method: 'DELETE' }).catch(() => null);
      if (r && !r.ok) { li.title = (await r.json()).detail || 'Cannot delete right now'; return; }
      if (s.id === state.current?.id) newSession();
      loadSessions();
    };
    ul.append(li);
  }
}
const clearLog = () => [...logEl.querySelectorAll('.msg, .alert')].forEach((n) => n.remove());
function openSession(id) {
  if (state.current?.id === id) return;
  state.current = { id };
  setBusy(false);
  clearLog();
  hero.hidden = true;
  openStream(id);                 // the snapshot renders the history and any live / paused turn
  renderSessions();
}
function newSession() {
  closeStream();                  // a running turn keeps going on the server
  state.current = null;
  setBusy(false);
  setAttention(false);
  clearLog();
  hero.hidden = false;
  $('#title').textContent = 'New session';
  renderSessions();
  renderTargetSelect();
  input.focus();
}
$('#btnNew').onclick = () => { newSession(); closeDrawer(); };

function renderSuggest() {
  const wrap = $('#suggest');
  wrap.innerHTML = '';
  for (const s of suggestions()) {
    const b = el('button', 'sg', `<span>${s.tag}</span>${esc(s.text)}`);
    b.type = 'button';
    b.onclick = () => { setMode(s.mode); send(s.text); };
    wrap.append(b);
  }
}

/* ---------------- machines (registry) ---------------- */

const TRANSPORT_LABEL = { 'winrm-https': 'WinRM over HTTPS', 'winrm-http': 'WinRM over HTTP', ssh: 'SSH' };
const TRANSPORT_PORT = { 'winrm-https': 5986, 'winrm-http': 5985, ssh: 22 };
const TRANSPORTS_FOR = { windows: ['winrm-http', 'winrm-https'], linux: ['ssh'] };

async function loadMachines() {
  try {
    const r = await fetch('/api/machines');
    if (r.ok) renderMachines(await r.json());
  } catch { /* gateway offline */ }
}

function machineState(m) {
  const port = m.status || { state: 'unknown' };
  const proto = m.transport === 'ssh' ? 'SSH' : 'WinRM';
  if (m.last_ok) return ['led-ok', `connected · ${m.os_info?.os?.replace(/^Microsoft\s+/, '') || proto}`, 'Connected. Tools can run on this machine.'];
  if (port.state === 'unreachable') return ['led-bad', `${proto} ${m.port} · unreachable`, `${proto} port ${m.port} did not answer (${port.error || 'no response'}).`];
  if (m.last_error) return ['led-bad', 'sign-in failed', m.last_error];
  if (!m.has_credentials) return ['led-warn', `${proto} ${m.port} · no credentials`, 'Click to enter the username and password Agentica should use.'];
  if (port.state === 'reachable') return ['led-warn', `${proto} ${m.port} · not tested`, 'Click to test the connection.'];
  return ['', 'checking…', 'Checking…'];
}

function renderMachines(data) {
  state.localHost = data.local.host;
  state.machines = data.machines;
  const ul = $('#machineList');
  ul.innerHTML = '';
  const local = el('li', 'local');
  local.innerHTML = `<span class="led led-ok"></span><span class="m-body"><span class="m-name">This PC</span><span class="m-sub">${esc(data.local.host.toLowerCase())} · local</span></span>`;
  local.title = 'Agentica runs here.';
  ul.append(local);
  for (const m of data.machines) {
    const [led, sub, tip] = machineState(m);
    const li = el('li');
    li.innerHTML = `<span class="led ${led}"></span><span class="m-body"><span class="m-name">${esc(m.label)}</span><span class="m-sub">${m.label !== m.host ? `${esc(m.host)} · ` : ''}${esc(sub)}</span></span><button class="s-del" type="button" aria-label="Remove ${esc(m.label)}"><svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg></button>`;
    li.title = tip;
    li.onclick = () => openConnect(m);
    li.querySelector('.s-del').onclick = async (e) => {
      e.stopPropagation();
      await fetch(`/api/machines/${m.id}`, { method: 'DELETE' }).catch(() => {});
      loadMachines();
    };
    ul.append(li);
  }
  renderTargetSelect();
}

function renderTargetSelect() {
  const sel = $('#targetSelect');
  const cur = (state.current ? state.current.target : state.defaultTarget) || '';
  const opts = [['', 'This PC'], ...state.machines.map((m) => [m.label, m.label])];
  if (cur && !state.machines.some((m) => m.label === cur)) opts.push([cur, `${cur} (removed)`]);
  const html = opts.map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
  if (sel.innerHTML !== html) sel.innerHTML = html;
  sel.value = cur;
  sel.closest('.target-pick').classList.toggle('remote', !!cur);
}
$('#targetSelect').onchange = (e) => {
  const v = e.target.value || null;
  if (state.current) {
    state.current.target = v;
    fetch(`/api/sessions/${state.current.id}`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target: v }) }).catch(() => {});
  }
  state.defaultTarget = v;
  store.set('agentica.target', v);
  renderTargetSelect();
};

/* connect dialog: credentials + connection test */
const cdlg = $('#connectDialog');
let connecting = null;
function showConnectResult(r) {
  const msg = $('#cdMsg');
  if (r.ok) {
    const i = r.info || {};
    msg.className = 'dlg-msg ' + (i.is_admin ? 'good' : 'warn');
    msg.textContent = `Connected to ${i.computer} · ${i.os || ''} · PowerShell ${i.ps_version || '?'} · signed in as ${i.user}`
      + (i.is_admin ? ' (administrator).' : '. Not an administrator: read-only tools work, service control will be refused.');
  } else {
    msg.className = 'dlg-msg bad';
    msg.textContent = r.error || 'Connection failed.';
  }
}
function openConnect(m) {
  connecting = m;
  $('#cdTitle').textContent = `Connect to ${m.label}`;
  $('#cdSub').textContent = `${m.host} · ${TRANSPORT_LABEL[m.transport] || m.transport} · port ${m.port}`;
  $('#cdUser').value = m.username || '';
  $('#cdPass').value = '';
  $('#cdPass').placeholder = m.has_credentials ? 'unchanged' : '';
  const msg = $('#cdMsg');
  msg.className = 'dlg-msg' + (m.last_error ? ' bad' : '');
  msg.textContent = m.last_ok ? `Last connected ${clock(m.last_ok * 1000)}.` : (m.last_error || '');
  $('#cdTest').disabled = !m.has_credentials;
  cdlg.showModal();
  (m.username ? $('#cdPass') : $('#cdUser')).focus();
}
async function connectAction(kind) {
  const m = connecting;
  const msg = $('#cdMsg');
  const buttons = cdlg.querySelectorAll('button');
  buttons.forEach((b) => (b.disabled = true));
  msg.className = 'dlg-msg';
  msg.textContent = `Connecting to ${m.host}…`;
  try {
    let r;
    if (kind === 'save') {
      r = await fetch(`/api/machines/${m.id}/credentials`, { method: 'PUT', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username: $('#cdUser').value.trim(), password: $('#cdPass').value }) });
    } else {
      r = await fetch(`/api/machines/${m.id}/test`, { method: 'POST' });
    }
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    showConnectResult(d);
    if (d.machine) connecting = d.machine;
    loadMachines();
  } catch (err) {
    msg.className = 'dlg-msg bad';
    msg.textContent = err.message;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
    $('#cdTest').disabled = !connecting?.has_credentials;
  }
}
$('#connectForm').addEventListener('submit', (e) => {
  e.preventDefault();
  if (!$('#cdUser').value.trim() || !$('#cdPass').value) {
    $('#cdMsg').className = 'dlg-msg bad';
    $('#cdMsg').textContent = 'Enter a username and password.';
    return;
  }
  connectAction('save');
});
$('#cdTest').onclick = () => connectAction('test');
$('#cdClose').onclick = () => cdlg.close();
$('#cdRemove').onclick = async () => {
  await fetch(`/api/machines/${connecting.id}`, { method: 'DELETE' }).catch(() => {});
  cdlg.close();
  loadMachines();
};

const dlg = $('#machineDialog');
function fillTransports() {
  const os = $('#mdOs').value;
  $('#mdTransport').innerHTML = TRANSPORTS_FOR[os].map((t) => `<option value="${t}">${TRANSPORT_LABEL[t]} · ${TRANSPORT_PORT[t]}</option>`).join('');
}
$('#mdOs').onchange = fillTransports;
$('#btnAddMachine').onclick = () => {
  fillTransports();
  $('#mdMsg').textContent = '';
  $('#mdMsg').className = 'dlg-msg';
  dlg.showModal();
  $('#mdHosts').focus();
};
$('#mdCancel').onclick = () => dlg.close();
$('#machineForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = $('#mdMsg');
  const hosts = $('#mdHosts').value.trim();
  if (!hosts) { msg.className = 'dlg-msg bad'; msg.textContent = 'Enter at least one IP address or hostname.'; return; }
  $('#mdSubmit').disabled = true;
  msg.className = 'dlg-msg'; msg.textContent = 'Adding and checking reachability…';
  try {
    const r = await fetch('/api/machines', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ hosts, os: $('#mdOs').value, transport: $('#mdTransport').value, label: $('#mdLabel').value,
                             username: $('#mdUser').value.trim(), password: $('#mdPass').value }) });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    const parts = [];
    if (d.added.length) parts.push(`Added ${d.added.length}: ${d.added.map((m) => `${m.label} (${machineState(m)[1]})`).join(', ')}.`);
    if (d.duplicates.length) parts.push(`Already listed: ${d.duplicates.join(', ')}.`);
    if (d.invalid.length) parts.push(`Not a valid IP or hostname: ${d.invalid.join(', ')}.`);
    msg.className = 'dlg-msg ' + (d.invalid.length && !d.added.length ? 'bad' : 'good');
    msg.textContent = parts.join(' ');
    if (d.added.length) { $('#mdHosts').value = ''; $('#mdLabel').value = ''; $('#mdPass').value = ''; }
    loadMachines();
  } catch (err) {
    msg.className = 'dlg-msg bad';
    msg.textContent = err.message;
  } finally {
    $('#mdSubmit').disabled = false;
  }
});

/* ---------------- models + health ---------------- */

async function loadModels() {
  try {
    const r = await fetch('/api/models');
    if (!r.ok) throw new Error();
    const { models } = await r.json();
    state.models = models;
    if (!models.find((m) => m.name === state.model)) state.model = (models.find((m) => /qwen/i.test(m.name)) || models[0])?.name || null;
    const sel = $('#modelSelect');
    const html = models.length ? models.map((m) => `<option value="${esc(m.name)}">${esc(m.name)}</option>`).join('') : '<option value="">no models</option>';
    if (sel.innerHTML !== html) sel.innerHTML = html;
    sel.value = state.model || '';
  } catch { /* offline — LED shows it */ }
  renderThink(); renderHint(); renderModelTile(); updateSend();
}
$('#modelSelect').onchange = (e) => {
  state.model = e.target.value;
  store.set('agentica.model', state.model);
  renderThink(); renderHint(); renderModelTile(); updateSend();
};

async function health() {
  const led = $('#statusLed'), pick = $('#modelPick');
  try {
    const r = await (await fetch('/api/health')).json();
    led.className = 'led ' + (r.ollama ? 'led-ok' : 'led-bad');
    pick.title = r.ollama ? `Ollama ${r.version} · online` : 'Ollama is not reachable';
  } catch {
    led.className = 'led led-bad';
    pick.title = 'Agentica gateway is offline';
  }
}

async function loadToolsets() {
  try {
    const [ts, tl] = await Promise.all([fetch('/api/toolsets').then((r) => r.json()), fetch('/api/tools').then((r) => r.json())]);
    state.toolsets = ts.toolsets;
    state.tools = tl.tools;
  } catch { state.toolsets = []; state.tools = []; }
  renderModes(); renderHint();
}

/* ---------------- system monitor (SSE, 1 s) ---------------- */

const SLOTS = 90;  // seconds of history the server keeps; short histories fill from the right
function sparkPath(vals, max, w, h, slots = SLOTS) {
  if (!vals || vals.length < 2) return { line: '', area: '' };
  const step = w / (slots - 1);
  const off = Math.max(slots - vals.length, 0);
  const pts = vals.slice(-slots).map((v, i) => `${((i + off) * step).toFixed(1)},${(h - 1 - (Math.min(v, max) / max) * (h - 3)).toFixed(1)}`);
  const line = 'M' + pts.join('L');
  return { line, area: `${line}L${w},${h}L${(off * step).toFixed(1)},${h}Z` };
}
function setSpark(svgEl, vals, max, w, h) {
  const p = sparkPath(vals, max, w, h);
  svgEl.querySelector('.line')?.setAttribute('d', p.line);
  svgEl.querySelector('.area')?.setAttribute('d', p.area);
}
function setVal(node, pct) { node.textContent = Math.round(pct) + '%'; node.className = 'mp-v ' + level(pct); }

function renderPill(t) {
  setVal($('#pCpu'), t.cpu.percent);
  setVal($('#pMem'), t.memory.percent);
  const sys = t.disks.find((d) => /^c:|^\/$/i.test(d.mount)) || t.disks[0];
  if (sys) setVal($('#pDisk'), sys.percent);
  $('#pSpark path').setAttribute('d', sparkPath(t.cpu.history.slice(-40), 100, 60, 16, 40).line);
}

let coresBuilt = 0;
function renderMonitor(t) {
  $('#mHost').textContent = `${t.host.hostname} · ${t.host.os.replace(/\s*\(.*\)/, '')} · ${uptime(t.host.uptime)}`;
  $('#mCpu').innerHTML = `${Math.round(t.cpu.percent)}<small>%</small>`;
  $('#mCores').textContent = `${t.cpu.physical ?? '?'}c / ${t.cpu.logical}t`;
  setSpark($('#mCpuSpark'), t.cpu.history, 100, 200, 44);
  const bars = $('#mCoreBars');
  if (coresBuilt !== t.cpu.per_core.length) { bars.innerHTML = t.cpu.per_core.map(() => '<i><b></b></i>').join(''); coresBuilt = t.cpu.per_core.length; }
  t.cpu.per_core.forEach((v, i) => { const b = bars.children[i].firstChild; b.style.height = Math.max(v, 4) + '%'; b.className = level(v); });

  $('#mMem').innerHTML = `${Math.round(t.memory.percent)}<small>%</small>`;
  $('#mMemText').textContent = `${gb(t.memory.used)} / ${gb(t.memory.total)} GB`;
  setSpark($('#mMemSpark'), t.mem_hist, 100, 200, 44);
  $('#mDisks').innerHTML = t.disks.map((d) => `<div class="disk"><div><b>${esc(d.mount)}</b><span>${gb(d.free)} GB free</span></div><div class="bar-m ${level(d.percent)}"><i style="width:${d.percent}%"></i></div></div>`).join('');

  $('#mRx').textContent = rate(t.net.rx);
  $('#mTx').textContent = rate(t.net.tx);
  const nmax = Math.max(1, ...t.net.rx_hist, ...t.net.tx_hist);
  const ns = $('#mNetSpark');
  ns.querySelector('.rx').setAttribute('d', sparkPath(t.net.rx_hist, nmax, 200, 44).line);
  ns.querySelector('.tx').setAttribute('d', sparkPath(t.net.tx_hist, nmax, 200, 44).line);

  $('#mProcs').innerHTML = t.procs.slice(0, 5).map((p) => `<tr><td title="${esc(p.name)} · pid ${p.pid}">${esc(p.name)}</td><td class="n${p.cpu >= 10 ? ' hi' : ''}">${p.cpu.toFixed(1)}%</td><td class="n">${Math.round(p.rss / 1024 ** 2)} MB</td></tr>`).join('');
}

function renderModelTile() {
  const m = modelInfo();
  $('#mModel').textContent = m ? m.name : '—';
  $('#mModelState').textContent = m ? (m.loaded ? 'in memory' : 'idle') : '—';
  const kv = m ? [['params', m.parameter_size], ['quant', m.quantization], ['context', m.context_length?.toLocaleString()], ['last run', state.lastTps ? state.lastTps.toFixed(1) + ' tok/s' : '—']] : [];
  $('#mModelKv').innerHTML = kv.map(([k, v]) => `<dt>${k}</dt><dd>${esc(v ?? '—')}</dd>`).join('');
}

/* remote machines: polled by the server every few seconds, delivered on the same SSE stream */
function renderFleetPill(f) {
  const list = Object.values(f?.machines || {});
  $('#pFleet').hidden = !list.length;
  if (!list.length) return;
  const up = list.filter((m) => m.state === 'ok').length;
  const v = $('#pFleetV');
  v.textContent = `${up}/${list.length}`;
  v.className = 'mp-v ' + (up === list.length ? '' : up ? 'warn' : 'hot');
}

function renderFleet(f) {
  const list = Object.values(f?.machines || {});
  $('#mFleet').hidden = !list.length;
  if (!list.length) return;
  const up = list.filter((m) => m.state === 'ok').length;
  $('#mFleetMeta').textContent = `${up}/${list.length} online · polled every ${f.interval}s`;
  const now = Date.now() / 1000;
  $('#mFleetGrid').innerHTML = list.map((m) => {
    const x = m.metrics;
    const ok = m.state === 'ok' && x;
    const led = ok ? 'led-ok' : m.state === 'waiting' ? '' : m.state === 'setup' ? 'led-warn' : 'led-bad';
    const age = m.updated ? `${Math.max(0, Math.round(now - m.updated))}s ago` : '';
    const head = `<div class="fc-head"><span class="led ${led}"></span><span class="fc-name" title="${esc(m.label)}">${esc(m.label)}</span><span class="fc-age">${ok ? age : esc(m.state === 'setup' ? 'needs setup' : m.state)}</span></div>`;
    const sub = `<div class="fc-sub">${esc(m.host)}${x?.os ? ` · ${esc(x.os.replace(/^Microsoft\s+/, ''))}` : ''}</div>`;
    if (!ok) {
      const why = m.state === 'waiting' ? 'Waiting for the first poll…' : (m.error || 'No data');
      const stale = x && m.updated ? ` Last data ${Math.round(now - m.updated)}s ago.` : '';
      return `<div class="fcard ${m.state === 'waiting' || m.state === 'setup' ? 'waiting' : 'down'}">${head}${sub}<div class="fc-err">${esc(why)}${stale}</div></div>`;
    }
    const mem = x.memory?.percent ?? 0, dsk = x.system_disk?.percent_used ?? 0;
    const spark = sparkPath(m.cpu_hist, 100, 120, 30, 40);
    return `<div class="fcard">${head}${sub}
      <div class="fc-row"><div class="fc-big">${Math.round(x.cpu_percent)}<small>%</small></div>
        <svg class="t-spark fc-spark" viewBox="0 0 120 30" preserveAspectRatio="none" aria-hidden="true"><path class="area" d="${spark.area}"/><path class="line" d="${spark.line}"/></svg></div>
      <div class="fc-stats"><span>MEM <b class="${level(mem)}">${Math.round(mem)}%</b></span><span>${esc(x.system_disk?.mount || 'disk')} <b class="${level(dsk)}">${Math.round(dsk)}%</b></span><span>${uptime(Math.round((x.uptime_hours || 0) * 3600))}</span><span>${x.processes} procs</span></div>
    </div>`;
  }).join('');
}

/* ---------------- applications (status monitoring) ---------------- */

function appChips(c) {
  const out = [];
  const chip = (ok, text) => out.push(`<span class="achip ${ok === true ? 'ok' : ok === false ? 'bad' : ''}">${esc(text)}</span>`);
  if (c.process) chip(c.process.ok, c.process.ok == null ? `${c.process.names.join(', ')} ?` : `${c.process.count}× ${c.process.names.join(', ')}`);
  if (c.process?.ok && c.process.memory_mb != null) {
    const mem = c.process.memory_mb >= 1024 ? `${(c.process.memory_mb / 1024).toFixed(1)} GB` : `${Math.round(c.process.memory_mb)} MB`;
    chip(null, `${c.process.cpu_percent ?? 0}% CPU · ${mem}`);
  }
  if (c.process?.not_responding) chip(false, `${c.process.not_responding} not responding`);
  if (c.service) chip(c.service.ok, `svc ${c.service.name} ${c.service.ok == null ? '?' : c.service.status}`);
  if (c.port) chip(c.port.ok, c.port.ok ? `:${c.port.port} ${c.port.latency_ms} ms` : `:${c.port.port} ✕`);
  if (c.http) chip(c.http.ok, c.http.ok ? `HTTP ${c.http.status} ${c.http.latency_ms} ms` : `HTTP ${c.http.status || '✕'}`);
  return out.join('');
}

function renderAppsPill(v) {
  const list = v?.apps || [];
  $('#pApps').hidden = !list.length;
  if (!list.length) return;
  const up = list.filter((a) => a.result?.status === 'up').length;
  const down = list.filter((a) => a.result?.status === 'down').length;
  const el_ = $('#pAppsV');
  el_.textContent = `${up}/${list.length}`;
  el_.className = 'mp-v ' + (down ? 'hot' : up === list.length ? '' : 'warn');
}

function renderApps(v) {
  const list = v?.apps || [];
  state.apps = list;
  const up = list.filter((a) => a.result?.status === 'up').length;
  $('#mAppsMeta').textContent = list.length ? `${up}/${list.length} up · checked every ${v.interval}s` : '';
  const grid = $('#mAppsGrid');
  if (!list.length) {
    grid.innerHTML = '<div class="apps-empty">No applications yet. Add one with + to see whether it is running and responding.</div>';
    return;
  }
  const now = Date.now() / 1000;
  grid.innerHTML = list.map((a) => {
    const r = a.result;
    const st = r?.status || 'waiting';
    const led = { up: 'led-ok', degraded: 'led-warn', down: 'led-bad' }[st] || '';
    const age = r?.checked ? `${Math.max(0, Math.round(now - r.checked))}s ago` : 'checking…';
    return `<div class="fcard appcard ${st}" data-id="${esc(a.id)}" title="Click to edit">
      <div class="fc-head"><span class="led ${led}"></span><span class="fc-name">${esc(a.name)}</span>
        ${r ? `<span class="app-state ${st}">${st.toUpperCase()}</span>` : ''}</div>
      <div class="fc-sub">${esc(a.machine || 'This PC')}${r?.since ? ` · ${st} since ${clock(r.since * 1000)}` : ''} · ${age}</div>
      ${r ? `<div class="app-sum">${esc(r.summary)}</div><div class="achips">${appChips(r.checks || {})}</div>` : '<div class="app-sum">Waiting for the first check…</div>'}
    </div>`;
  }).join('');
}
$('#mAppsGrid').addEventListener('click', (e) => {
  const card = e.target.closest('.fcard.appcard');
  if (card) openAppDialog((state.apps || []).find((a) => a.id === card.dataset.id));
});

/* add / edit dialog */
const adlg = $('#appDialog');
let editingApp = null;
function showAppResult(r) {
  const msg = $('#adMsg');
  if (!r) return;
  msg.className = 'dlg-msg ' + ({ up: 'good', degraded: 'warn', down: 'bad' }[r.status] || '');
  msg.textContent = `${r.status.toUpperCase()} · ${r.summary}`;
  const h = $('#adHist');
  h.hidden = !r.history?.length;
  h.innerHTML = (r.history || []).slice(0, 5).map((e) => {
    const d = new Date(e.ts * 1000);
    return `<li><b class="${esc(e.status)}">${esc(e.status)}</b> · ${d.toLocaleDateString([], { month: 'short', day: 'numeric' })} ${clock(e.ts * 1000)}</li>`;
  }).join('');
}

/* "Pick a running app": friendly names, process name, suggested ports */
let pickApps = [];
async function loadPickList() {
  const list = $('#adPickList');
  pickApps = [];
  try {
    const q = new URLSearchParams({ machine: $('#adMachine').value, background: $('#adBg').checked ? 'true' : 'false' });
    const r = await fetch(`/api/apps/discover?${q}`);
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    pickApps = d.apps;
  } catch (err) {
    list.hidden = false;
    list.innerHTML = `<li class="pk-empty">${esc(err.message)}</li>`;
    return;
  }
  if (document.activeElement === $('#adPick')) renderPickList();
}
function renderPickList() {
  const q = $('#adPick').value.trim().toLowerCase();
  const hits = pickApps.filter((a) => !q || a.display.toLowerCase().includes(q) || a.process.toLowerCase().includes(q)).slice(0, 40);
  const list = $('#adPickList');
  list.hidden = false;
  list.innerHTML = hits.length ? hits.map((a, i) => `<li data-i="${pickApps.indexOf(a)}">
      <span class="pk-name">${esc(a.display)}</span>
      <span class="pk-meta">${esc(a.process)} · ${a.count}× · ${a.memory_mb >= 1024 ? (a.memory_mb / 1024).toFixed(1) + ' GB' : Math.round(a.memory_mb) + ' MB'}${a.ports?.length ? ' · ports ' + a.ports.slice(0, 3).join(', ') : ''}</span></li>`).join('')
    : `<li class="pk-empty">${pickApps.length ? 'No running app matches.' : 'Loading…'}</li>`;
}
$('#adPick').addEventListener('focus', renderPickList);
$('#adPick').addEventListener('input', renderPickList);
$('#adPick').addEventListener('blur', () => setTimeout(() => ($('#adPickList').hidden = true), 150));
$('#adBg').onchange = loadPickList;
$('#adMachine').onchange = () => { $('#adPorts').hidden = true; loadPickList(); };
$('#adPickList').addEventListener('mousedown', (e) => {
  const li = e.target.closest('li[data-i]');
  if (!li) return;
  e.preventDefault();
  const a = pickApps[+li.dataset.i];
  $('#adName').value = a.display.slice(0, 40);
  $('#adProcess').value = a.process;
  $('#adPick').value = a.display;
  $('#adPickList').hidden = true;
  const ports = $('#adPorts');
  ports.hidden = !a.ports?.length;
  ports.innerHTML = a.ports?.length
    ? `Listening on: ${a.ports.map((p) => `<button type="button" data-port="${p}" title="Add a port check">${p}</button>`).join('')}`
    : '';
});
$('#adPorts').addEventListener('click', (e) => {
  const b = e.target.closest('button[data-port]');
  if (b) $('#adPort').value = b.dataset.port;
});
function openAppDialog(a = null) {
  editingApp = a;
  $('#adTitle').textContent = a ? `Edit ${a.name}` : 'Add application';
  $('#adMachine').innerHTML = [['', 'This PC'], ...state.machines.map((m) => [m.label, m.label])]
    .map(([v, t]) => `<option value="${esc(v)}">${esc(t)}</option>`).join('');
  $('#adName').value = a?.name || '';
  $('#adMachine').value = a?.machine || '';
  $('#adProcess').value = a?.process || '';
  $('#adService').value = a?.service || '';
  $('#adPort').value = a?.port || '';
  $('#adUrl').value = a?.url || '';
  $('#adRemove').hidden = !a;
  $('#adCheck').hidden = !a;
  $('#adMsg').className = 'dlg-msg';
  $('#adMsg').textContent = '';
  $('#adHist').hidden = true;
  $('#adPick').value = '';
  $('#adPorts').hidden = true;
  $('#adPickList').hidden = true;
  $('.picker').hidden = !!a;                        // picking is for new apps
  if (a?.result) showAppResult(a.result);
  adlg.showModal();
  if (!a) { loadPickList(); $('#adPick').focus(); } else $('#adName').focus();
}
async function appRequest(method, url, body) {
  const buttons = adlg.querySelectorAll('button');
  buttons.forEach((b) => (b.disabled = true));
  $('#adMsg').className = 'dlg-msg';
  $('#adMsg').textContent = 'Checking…';
  try {
    const r = await fetch(url, { method, headers: { 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    const d = await r.json();
    if (!r.ok) throw new Error(d.detail || `HTTP ${r.status}`);
    return d;
  } catch (err) {
    $('#adMsg').className = 'dlg-msg bad';
    $('#adMsg').textContent = err.message;
    return null;
  } finally {
    buttons.forEach((b) => (b.disabled = false));
  }
}
$('#appForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const body = { name: $('#adName').value, machine: $('#adMachine').value, process: $('#adProcess').value,
                 service: $('#adService').value, port: $('#adPort').value, url: $('#adUrl').value };
  const d = await appRequest(editingApp ? 'PUT' : 'POST', editingApp ? `/api/apps/${editingApp.id}` : '/api/apps', body);
  if (d) {
    editingApp = d;
    $('#adTitle').textContent = `Edit ${d.name}`;
    $('#adRemove').hidden = false;
    $('#adCheck').hidden = false;
    showAppResult(d.result);
  }
});
$('#btnAddApp').onclick = (e) => { e.stopPropagation(); openAppDialog(); };
$('#adCheck').onclick = async () => { const d = await appRequest('POST', `/api/apps/${editingApp.id}/check`); if (d) showAppResult(d.result); };
$('#adClose').onclick = () => adlg.close();
$('#adRemove').onclick = async () => { if (await appRequest('DELETE', `/api/apps/${editingApp.id}`)) adlg.close(); };

function onTelemetry(t) {
  const hostChanged = state.host?.hostname !== t.host.hostname;
  state.telemetry = t;
  state.host = t.host;
  if (hostChanged) renderSuggest();
  renderPill(t);
  renderFleetPill(t.fleet);
  renderAppsPill(t.apps);
  if (state.monitorOpen) { renderMonitor(t); renderFleet(t.fleet); renderApps(t.apps); }
}

let es = null;
function startTelemetry() {
  if (es) return;
  es = new EventSource('/api/telemetry/stream');
  es.onmessage = (e) => { $('#monLed').className = 'led led-ok'; onTelemetry(JSON.parse(e.data)); };
  es.onerror = () => { $('#monLed').className = 'led led-bad'; };   // EventSource reconnects by itself
}
function stopTelemetry() { es?.close(); es = null; }
document.addEventListener('visibilitychange', () => (document.hidden ? stopTelemetry() : startTelemetry()));

function setMonitor(open) {
  state.monitorOpen = open;
  store.set('agentica.monitor', open);
  $('#monitor').hidden = !open;
  $('#monPill').setAttribute('aria-expanded', String(open));
  if (open) { renderModelTile(); if (state.telemetry) { renderMonitor(state.telemetry); renderFleet(state.telemetry.fleet); renderApps(state.telemetry.apps); } }
}
$('#monPill').onclick = () => setMonitor(!state.monitorOpen);
$('#monMin').onclick = () => setMonitor(false);

/* ---------------- chrome ---------------- */

const app = $('#app');
const narrow = () => matchMedia('(max-width: 860px)').matches;
function closeDrawer() { app.classList.remove('drawer'); }
$('#btnSide').onclick = () => {
  if (narrow()) app.classList.toggle('drawer');
  else { app.classList.toggle('side-off'); store.set('agentica.sideOff', app.classList.contains('side-off')); }
};
$('#scrim').onclick = closeDrawer;
$('#btnTheme').onclick = () => {
  const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
  document.documentElement.dataset.theme = next;
  try { localStorage.setItem('agentica.theme', next); } catch { /* storage unavailable */ }
};
logEl.addEventListener('click', (e) => {
  const b = e.target.closest('.code-copy');
  if (!b) return;
  navigator.clipboard?.writeText(b.closest('.codeblock').querySelector('pre').textContent)
    .then(() => { b.textContent = 'Copied'; setTimeout(() => (b.textContent = 'Copy'), 1400); });
});
document.addEventListener('keydown', (e) => {
  if (e.altKey && !e.ctrlKey && !e.metaKey) {
    const k = e.key.toLowerCase();
    if (k === 't') { e.preventDefault(); if (!btnThink.disabled) btnThink.click(); }
    if (k === 'n') { e.preventDefault(); newSession(); }
    if (k === 'm') { e.preventDefault(); setMonitor(!state.monitorOpen); }
  }
  if (e.key === 'Escape') {
    if (dlg.open || cdlg.open || adlg.open) return;    // dialogs close themselves
    if (state.busy) cancelRun();
    closeDrawer();
  }
  if (e.key === '/' && !/INPUT|TEXTAREA|SELECT/.test(document.activeElement?.tagName)) { e.preventDefault(); input.focus(); }
});

/* ---------------- boot ---------------- */

(function boot() {
  if (store.get('agentica.sideOff', false)) app.classList.add('side-off');
  renderModes(); renderHint(); renderThink(); renderSuggest();
  setMonitor(state.monitorOpen);
  autosize(); updateSend();
  health(); setInterval(health, 8000);
  try { localStorage.removeItem('agentica.sessions.v1'); } catch { /* history now lives on the server */ }
  Promise.all([loadModels(), loadToolsets(), loadSessions()]).then(() => {
    const waiting = state.sessions.find((x) => x.state === 'paused');   // e.g. after a server restart
    if (waiting) openSession(waiting.id);
  });
  setInterval(loadModels, 15000);
  loadMachines(); setInterval(loadMachines, 15000);
  startTelemetry();
  input.focus();
})();
