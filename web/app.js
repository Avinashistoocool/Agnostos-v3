const $ = (s, r = document) => r.querySelector(s);
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
let token = localStorage.getItem('agn_token') || '';
let currentJob = null;

async function api(path, opts = {}) {
  const headers = { Authorization: `Bearer ${token}`, ...(opts.body && !(opts.body instanceof FormData) ? { 'Content-Type': 'application/json' } : {}) };
  const r = await fetch(path, { ...opts, headers, body: opts.body instanceof FormData ? opts.body : opts.body && JSON.stringify(opts.body) });
  if (r.status === 401) { signOut(); throw new Error('signed out'); }
  const ct = r.headers.get('content-type') || '';
  const data = ct.includes('json') ? await r.json() : await r.text();
  if (!r.ok) {
    const detail = data.detail || data || r.statusText;
    throw new Error(Array.isArray(detail) ? detail.map(x => `${x.loc.join('.')}: ${x.msg}`).join('; ') : detail);
  }
  return data;
}

// ---------- auth
$('#auth-form').addEventListener('click', async (e) => {
  const mode = e.target.dataset.mode; if (!mode) return;
  e.preventDefault();
  const f = new FormData($('#auth-form'));
  try {
    const res = await fetch(`/api/${mode}`, { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: f.get('email'), password: f.get('password') }) });
    const data = await res.json();
    if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : 'Check your email and password');
    token = data.token; localStorage.setItem('agn_token', token); boot();
  } catch (err) { $('#auth-msg').textContent = err.message; }
});
function signOut() { token = ''; localStorage.removeItem('agn_token'); location.reload(); }
$('#logout').onclick = async () => { try { await api('/api/logout', { method: 'POST' }); } catch {} signOut(); };

// ---------- tabs
const TABS = ['Overview', 'Researchers', 'Setup', 'Pipeline', 'Replies', 'Schedule'];
function showTab(name) {
  document.querySelectorAll('[data-tab]').forEach((s) => s.classList.toggle('hidden', s.dataset.tab !== name));
  document.querySelectorAll('#tabs button').forEach((b) => b.className = 'rounded-full px-3 py-1.5 ' + (b.textContent === name ? 'bg-coral' : 'text-muted hover:text-ink'));
  if (name === 'Overview') loadStats();
  if (name === 'Replies') loadReplies();
  if (name === 'Researchers') loadResearchers();
}
$('#tabs').innerHTML = TABS.map((t) => `<button type="button">${t}</button>`).join('');
$('#tabs').addEventListener('click', (e) => e.target.tagName === 'BUTTON' && showTab(e.target.textContent));

// ---------- overview
async function loadStats() {
  const s = await api('/api/stats');
  if (s.empty) { $('#kpis').innerHTML = `<div class="card p-6 col-span-full text-muted">No workbook yet. Go to <b>Pipeline</b> and run <b>Discover</b>, or upload one in <b>Setup</b>.</div>`; return; }
  const c = s.counts, rep = s.reply || {};
  const k = [['Professors', c.total], ['With email', c.with_email], ['Drafted', c.drafted], ['Sent', c.sent], ['Replied', rep.replied || 0]];
  $('#kpis').innerHTML = k.map(([l, v], i) => `<div class="card p-5 ${['', 'bg-sage', 'bg-lavender', 'bg-coral/40', ''][i]}"><p class="text-sm text-muted">${l}</p><p class="text-4xl font-medium tracking-tight mt-1">${v ?? 0}</p></div>`).join('');
  const rows = (o) => Object.entries(o || {}).sort((a, b) => b[1] - a[1]).map(([k, v]) => `<div class="flex justify-between"><span class="text-muted">${esc(k)}</span><b>${v}</b></div>`).join('') || '<p class="text-muted">—</p>';
  $('#send-break').innerHTML = rows(s.send);
  $('#llm-break').innerHTML = rows(s.llm);
}
$('#dl').onclick = async () => {
  const r = await fetch('/api/download/workbook', { headers: { Authorization: `Bearer ${token}` } });
  if (!r.ok) return alert('No workbook yet');
  const a = Object.assign(document.createElement('a'), { href: URL.createObjectURL(await r.blob()), download: 'agnostos-professors.xlsx' }); a.click();
};

// ---------- setup
const GROUPS = {
  'Language model': [['LLM_PROVIDER', 'groq or openai'], ['GROQ_API_KEY', 'free at console.groq.com', 'password'], ['OPENAI_API_KEY', '', 'password'], ['OPENAI_BASE_URL', 'optional proxy'], ['DRAFT_MODEL', 'e.g. gpt-5-mini']],
  'About you': [['POSITION', 'summer research internship (undergraduate)'], ['GEOGRAPHY', 'Europe (EU + Switzerland + UK)'], ['AVAILABILITY', 'May-July 2027, 8-12 weeks'], ['DISCOVER_QUERIES', 'topic a; topic b']],
  'Sending mailbox (SMTP)': [['SMTP_HOST', 'smtp.gmail.com'], ['SMTP_PORT', '465 or 587'], ['SMTP_SECURITY', 'ssl or starttls'], ['SMTP_USER', ''], ['SMTP_PASSWORD', 'app password', 'password'], ['SMTP_FROM', 'you@uni.edu'], ['SMTP_FROM_NAME', '']],
  'Reading replies (IMAP, optional)': [['IMAP_HOST', 'defaults to imap.<smtp domain>'], ['IMAP_USER', ''], ['IMAP_PASSWORD', '', 'password']],
  'Pacing': [['DAILY_SEND_CAP', '40'], ['SEND_DELAY_MIN', '300'], ['SEND_DELAY_MAX', '600'], ['MAX_PROFESSORS', '300'], ['BUDGET_USD', '5']],
};
function renderSettings(values) {
  $('#settings-groups').innerHTML = Object.entries(GROUPS).map(([g, fields]) => `
    <fieldset><legend class="font-medium mb-3">${g}</legend><div class="grid sm:grid-cols-2 gap-3">
    ${fields.map(([k, ph, type]) => `<label class="text-xs text-muted">${k}<input class="field mt-1 text-sm text-ink" name="${k}" type="${type || 'text'}" placeholder="${esc(ph)}" value="${esc(values[k] || '')}"></label>`).join('')}
    </div></fieldset>`).join('');
}
$('#settings').onsubmit = async (e) => {
  e.preventDefault();
  const body = Object.fromEntries([...new FormData(e.target)].filter(([, v]) => v !== ''));
  try { await api('/api/settings', { method: 'PUT', body }); $('#settings-msg').textContent = 'Saved.'; } catch (err) { $('#settings-msg').textContent = err.message; }
};
function renderUploads(files) {
  const items = [['resume', 'Resume (PDF/DOCX)', '.pdf,.docx'], ['cv', 'CV to attach (PDF)', '.pdf'], ['targets', 'Professor list (.xlsx, optional)', '.xlsx']];
  $('#uploads').innerHTML = items.map(([k, label, acc]) => `
    <label class="block bg-stone-50 rounded-3xl p-4 border border-dashed border-stone-300 cursor-pointer hover:bg-sage">
      <p class="font-medium">${label}</p><p class="text-muted text-xs mt-1">${files[k] ? '✓ ' + esc(files[k]) : 'click to upload'}</p>
      <input type="file" class="hidden" accept="${acc}" data-kind="${k}"></label>`).join('');
  $('#uploads').querySelectorAll('input').forEach((inp) => inp.onchange = async () => {
    const fd = new FormData(); fd.append('file', inp.files[0]);
    try { await api(`/api/upload/${inp.dataset.kind}`, { method: 'POST', body: fd }); loadMe(); } catch (err) { alert(err.message); }
  });
}

// ---------- pipeline tools
const TOOLS = [
  ['profile', 'Read resume', 'Check what was extracted from your resume.', []],
  ['tls-check', 'Connection check', 'Test SMTP, IMAP and model endpoints.', []],
  ['discover', 'Discover professors', 'Find people publishing in your topics.', [['count', 'number', 'how many', 300], ['batches', 'number', 'batches', 3], ['countries', 'text', 'europe | de,ch,gb', 'europe'], ['verify_emails', 'checkbox', 'find emails too', true]]],
  ['verify', 'Verify emails', 'Check and repair addresses.', [['repair', 'checkbox', 'repair', true], ['apply', 'checkbox', 'apply fixes', true]]],
  ['run', 'Score + draft', 'Match and draft one honest email each.', [['max_professors', 'number', 'max professors', 100], ['budget', 'number', 'budget USD', 2]]],
  ['send', 'Send review copies', 'Mail a few drafts to yourself first.', [['review', 'checkbox', 'to me', true], ['top', 'number', 'how many', 3]]],
  ['send', 'Send for real', 'Paced, inside their local hours.', [['live', 'checkbox', 'live', true], ['limit', 'number', 'max today', 40], ['local_window', 'text', 'window', '9-17'], ['wait', 'checkbox', 'wait for windows', true]], 'Send real emails to professors now?'],
];
$('#tools').innerHTML = TOOLS.map(([cmd, title, desc, fields, confirm], i) => `
  <form class="card p-6 space-y-3" data-tool="${i}">
    <h3 class="font-medium">${title}</h3><p class="text-sm text-muted">${desc}</p>
    <div class="grid grid-cols-2 gap-2">${fields.map(([k, t, ph, v]) => t === 'checkbox'
      ? `<label class="text-sm flex items-center gap-2"><input type="checkbox" name="${k}" ${v ? 'checked' : ''}> ${ph}</label>`
      : `<label class="text-xs text-muted">${ph}<input class="field mt-1 text-sm text-ink" type="${t}" name="${k}" value="${v ?? ''}" step="any"></label>`).join('')}</div>
    <button class="pill ${cmd === 'send' && fields.some(f => f[0] === 'live') ? 'bg-ink text-cream' : 'bg-coral'}">Run</button>
  </form>`).join('');
$('#tools').addEventListener('submit', async (e) => {
  e.preventDefault();
  const [cmd, , , fields, confirmMsg] = TOOLS[+e.target.dataset.tool];
  if (confirmMsg && !confirm(confirmMsg)) return;
  const options = {};
  for (const [k, t] of fields) {
    const el = e.target.elements[k];
    if (t === 'checkbox') { if (el.checked) options[k] = true; } else if (el.value !== '') options[k] = el.value;
  }
  runJob(cmd, options);
});
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-run]'); if (!b) return;
  if (b.dataset.confirm && !confirm(b.dataset.confirm)) return;
  const { command, options } = JSON.parse(b.dataset.run); runJob(command, options);
});
async function runJob(command, options) {
  try { const { id } = await api('/api/jobs', { method: 'POST', body: { command, options } }); await loadJobs(); openJob(id); }
  catch (err) { alert(err.message); }
}

// ---------- jobs
async function loadJobs() {
  const jobs = await api('/api/jobs');
  const dot = { running: 'bg-coral animate-pulse', done: 'bg-green-400', failed: 'bg-red-400', cancelled: 'bg-stone-300', interrupted: 'bg-stone-300' };
  $('#jobs').innerHTML = jobs.map((j) => `<li><button class="w-full text-left rounded-xl px-3 py-2 hover:bg-stone-50 ${j.id === currentJob ? 'bg-stone-100' : ''}" data-job="${j.id}">
    <span class="inline-block w-2 h-2 rounded-full ${dot[j.status] || ''} mr-2"></span>#${j.id} ${esc(j.command)}<br><span class="text-xs text-muted">${esc(j.started_at)}</span></button></li>`).join('') || '<li class="text-muted">No jobs yet.</li>';
  return jobs;
}
$('#jobs').addEventListener('click', (e) => { const b = e.target.closest('[data-job]'); if (b) openJob(+b.dataset.job); });
async function openJob(id) { currentJob = id; await refreshLog(); loadJobs(); }
async function refreshLog() {
  if (!currentJob) return;
  const log = await api(`/api/jobs/${currentJob}/log?tail=400`);
  const pre = $('#log'); const atBottom = pre.scrollTop + pre.clientHeight >= pre.scrollHeight - 30;
  pre.textContent = log || '(no output yet)'; if (atBottom) pre.scrollTop = pre.scrollHeight;
  const jobs = await api('/api/jobs'); const j = jobs.find((x) => x.id === currentJob);
  $('#cancel').classList.toggle('hidden', !j || j.status !== 'running');
}
$('#cancel').onclick = async () => { await api(`/api/jobs/${currentJob}/cancel`, { method: 'POST' }); refreshLog(); loadJobs(); };

// ---------- replies
async function loadReplies() {
  const items = await api('/api/replies');
  $('#reply-list').innerHTML = items.map((q, i) => `
    <div class="card p-6 ${q.sent_at ? 'opacity-60' : ''}">
      <div class="flex justify-between gap-3 flex-wrap"><div><p class="font-medium">${esc(q.name)} <span class="text-muted text-sm">${esc(q.email)}</span></p>
      <p class="text-sm text-muted">${esc(q.summary)}</p></div>
      <span class="text-xs rounded-full px-3 py-1 h-fit ${q.action === 'reply' ? 'bg-coral' : 'bg-sage'}">${esc(q.action)}${q.sent_at ? ' · sent' : ''}</span></div>
      <blockquote class="mt-4 text-sm bg-lavender rounded-2xl p-4 whitespace-pre-wrap">${esc(q.their_message)}</blockquote>
      <textarea class="w-full mt-3 rounded-2xl bg-stone-50 border border-stone-200 p-4 text-sm min-h-[140px]" data-i="${i}">${esc(q.body)}</textarea>
      <div class="flex gap-3 items-center mt-2"><label class="text-sm flex items-center gap-2"><input type="checkbox" data-approve="${i}" ${q.approved ? 'checked' : ''} ${q.sent_at ? 'disabled' : ''}> approved</label>
      <button class="pill bg-white border border-stone-200 text-sm" data-save="${i}">Save edit</button></div>
    </div>`).join('') || '<div class="card p-6 text-muted">No reply drafts yet. Click <b>Draft replies</b>.</div>';
}
$('#reply-list').addEventListener('click', async (e) => {
  const s = e.target.dataset.save; if (s === undefined) return;
  await api('/api/replies', { method: 'PUT', body: { index: +s, body: $(`textarea[data-i="${s}"]`).value } }); e.target.textContent = 'Saved';
});
$('#reply-list').addEventListener('change', async (e) => {
  const a = e.target.dataset.approve; if (a === undefined) return;
  await api('/api/replies', { method: 'PUT', body: { index: +a, approved: e.target.checked } });
});

// ---------- schedule
$('#schedule').onsubmit = async (e) => {
  e.preventDefault(); const f = e.target.elements;
  try { await api('/api/schedule', { method: 'PUT', body: { enabled: f.enabled.checked, time: f.time.value, limit: +f.limit.value, local_window: f.local_window.value } });
    $('#sched-msg').textContent = 'Saved.'; } catch (err) { $('#sched-msg').textContent = err.message; }
};

// ---------- boot
async function loadMe() {
  const me = await api('/api/me');
  renderSettings(me.settings); renderUploads(me.files);
  const s = me.schedule || {}; const f = $('#schedule').elements;
  f.enabled.checked = !!s.enabled; if (s.time) f.time.value = s.time; if (s.limit) f.limit.value = s.limit; if (s.local_window) f.local_window.value = s.local_window;
}
async function boot() {
  if (!token) return;
  try { await loadMe(); } catch { return; }
  $('#auth').classList.add('hidden'); $('#app').classList.remove('hidden');
  $('#tabs').classList.replace('hidden', 'flex'); $('#logout').classList.remove('hidden');
  showTab(location.hash === '#setup' ? 'Setup' : 'Overview');
  const jobs = await loadJobs(); if (jobs[0]) openJob(jobs[0].id);
  setInterval(() => { refreshLog(); loadJobs(); }, 4000);
}
boot();
