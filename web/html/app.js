/* 拆單專案管理 ─ 單頁前端 (vanilla JS, hash routing) */
const $app = document.getElementById('app');
const state = { catalog: null, lookups: null, customers: null, colors: null, collapsed: new Set(), tab: 'parts' };
const AUTO_FIELDS = ['edge_l', 'edge_w', 'mark_p', 'mark_q', 'mark_r', 'reminder'];
const STATUS = { draft: '草稿', confirmed: '已確認', producing: '生產中', done: '完成' };

// ───────── helpers ─────────
async function api(path, opt = {}) {
  const isForm = opt.body instanceof FormData;
  const res = await fetch('/api' + path, {
    ...opt,
    headers: isForm ? {} : { 'Content-Type': 'application/json' },
    body: isForm ? opt.body : opt.body ? JSON.stringify(opt.body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : JSON.stringify(data.detail || res.statusText));
  return data;
}
function toast(msg, err = false) {
  const t = document.getElementById('toast');
  t.textContent = msg; t.className = 'toast show' + (err ? ' err' : '');
  setTimeout(() => (t.className = 'toast'), err ? 4000 : 2000);
}
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
const num = (v) => (v === null || v === undefined || v === '' ? '' : (+v).toLocaleString('zh-TW', { maximumFractionDigits: 2 }));
// 下拉選項；目前值不在清單內時也列出來，避免一改別格就被清空
const opt = (list, cur, blank = true) => {
  const all = cur !== null && cur !== undefined && cur !== '' && !list.some((v) => v == cur) ? [...list, cur] : list;
  return (blank ? `<option value="">-</option>` : '') + all.map((v) => `<option value="${esc(v)}" ${v == cur ? 'selected' : ''}>${esc(v)}</option>`).join('');
};
const n0 = (v) => (v === '' || v === null || v === undefined ? null : +v);
const today = () => new Date().toISOString().slice(0, 10);

// 常用板厚下拉 (清單來自基礎資料 → 下拉清單 → 板厚)；旁邊 ＋ 可直接新增
function thicknessSelect(cur) {
  const list = (state.lookups['板厚'] || []).map(Number).sort((a, b) => b - a);
  const curN = cur != null ? +cur : (list[0] ?? 18);
  return `<select name="board_thickness" required>${opt(list, curN, false)}</select><button type="button" class="link small" data-addthick title="新增常用板厚">＋</button>`;
}
async function addThickness(selectEl) {
  const v = prompt('新增常用板厚 (mm)，例如 17.2：');
  if (!v) return;
  try {
    state.lookups = await api('/master/lookups', { method: 'POST', body: { kind: '板厚', value: v.trim() } });
    const list = (state.lookups['板厚'] || []).map(Number).sort((a, b) => b - a);
    selectEl.innerHTML = opt(list, +v, false); toast(`已加入板厚 ${v}`);
  } catch (err) { toast(err.message, true); }
}
document.addEventListener('click', (e) => {
  const b = e.target.closest('[data-addthick]');
  if (b) addThickness(b.previousElementSibling);
});

async function ensureMaster() {
  if (!state.catalog) state.catalog = await api('/master/parts-catalog');
  if (!state.lookups) state.lookups = await api('/master/lookups');
  if (!state.customers) state.customers = await api('/customers');
  if (!state.colors) state.colors = await api('/master/colors?limit=3000');
}
const allPartNames = () => [...new Set(Object.values(state.catalog).flat())];
const colorDatalist = () => `<datalist id="colors">${state.colors.map((c) => `<option value="${esc(c.code)}">${esc(c.board_name || '')} ${esc(c.vendor || '')}</option>`).join('')}</datalist>`;
const nameDatalist = () => `<datalist id="partnames">${allPartNames().map((n) => `<option value="${esc(n)}">`).join('')}</datalist>`;

// 客戶下拉：含「＋ 新增客戶…」；選到客戶時把 業務/設計師 帶成客戶名稱 (空白時)
const customerOptions = (cur) => `<option value="">-</option>${state.customers.map((c) => `<option value="${c.id}" ${c.id == cur ? 'selected' : ''}>${esc(c.code || '')} ${esc(c.name)}</option>`).join('')}<option value="__new__">＋ 新增客戶…</option>`;
function wireCustomerSelect(sel, designerInput) {
  let prev = sel.value;
  sel.onchange = async () => {
    if (sel.value === '__new__') {
      sel.value = prev;
      const c = await newCustomerModal();
      if (c) { state.customers = await api('/customers'); sel.innerHTML = customerOptions(c.id); prev = String(c.id); if (designerInput && !designerInput.value) designerInput.value = c.name; }
      return;
    }
    prev = sel.value;
    const c = state.customers.find((x) => String(x.id) === sel.value);
    if (c && designerInput && (!designerInput.value || state.customers.some((x) => x.name === designerInput.value))) designerInput.value = c.name;
  };
}
function newCustomerModal() {
  return new Promise((resolve) => {
    let v = document.getElementById('cmodal');
    if (!v) { v = document.createElement('div'); v.id = 'cmodal'; v.className = 'modal'; document.body.appendChild(v); }
    v.style.display = 'flex';
    v.innerHTML = `<div class="modal-box" style="width:min(96vw,720px)"><div class="row" style="justify-content:space-between"><b>新增客戶</b><button type="button" id="cmclose">關閉</button></div>
      <form id="cmform" class="row">
        <label>客戶編號 <input name="code" placeholder="AA0B001"></label><label>設計師/業務 <input name="name" required autofocus></label><label>聯絡電話 <input name="contact_phone"></label>
        <label>公司名稱 <input name="company_name"></label><label>統編 <input name="tax_id"></label><label>公司地址 <input name="address" style="min-width:240px"></label>
        <label>板材折數 <input class="num" name="board_discount" type="number" step="0.001" placeholder="例 0.41"></label><label>安裝折數 <input class="num" name="install_discount" type="number" step="0.001" placeholder="例 0.2"></label>
        <button class="primary">建立並選用</button></form></div>`;
    const close = (r) => { v.style.display = 'none'; resolve(r); };
    v.querySelector('#cmclose').onclick = () => close(null);
    v.onclick = (e) => { if (e.target === v) close(null); };
    v.querySelector('#cmform').onsubmit = async (e) => {
      e.preventDefault();
      const f = Object.fromEntries(new FormData(e.target));
      for (const k of ['board_discount', 'install_discount']) f[k] = n0(f[k]);
      for (const k in f) if (f[k] === '') f[k] = null;
      try { const c = await api('/customers', { method: 'POST', body: f }); toast(`已建立客戶 ${c.name}`); close(c); } catch (err) { toast(err.message, true); }
    };
    setTimeout(() => v.querySelector('[name=name]').focus(), 50);
  });
}

// ───────── router ─────────
const routes = { '': pageProjects, projects: pageProjects, project: pageProject, customers: pageCustomers, master: pageMaster, feedback: pageFeedback, updates: pageUpdates, changelog: pageUpdates };
async function route() {
  const [name, ...args] = location.hash.replace(/^#\/?/, '').split('/');
  const fn = routes[name] || pageProjects;
  try { await fn(...args); } catch (e) { $app.innerHTML = `<div class="card">錯誤：${esc(e.message)}</div>`; }
}
window.addEventListener('hashchange', route);
route();
// 目前頁面對應的導覽名稱
function tourName() {
  const h = location.hash;
  if (h.startsWith('#/project/')) return 'project-' + (h.split('/')[3] || 'parts');
  if (h.startsWith('#/customers')) return 'customers';
  if (h.startsWith('#/master')) return 'master';
  if (h.startsWith('#/feedback')) return 'feedback';
  if (h.startsWith('#/updates') || h.startsWith('#/changelog')) return 'updates';
  return 'projects';
}

// ───────── 版本號 / 意見回饋 ─────────
api('/version').then((v) => { document.getElementById('verbadge').textContent = 'v' + v.version; checkNewVersion(v.version); }).catch(() => {});
const FB_CAT = { bug: '問題（哪裡怪怪的／算錯／按了沒反應）', feature: '需求（希望多一個功能或改流程）', question: '疑問（不知道怎麼操作）', other: '其他' };
const FB_STATUS = { new: '新', planned: '已排程', done: '已完成', rejected: '不處理' };
document.getElementById('fbbtn').onclick = () => openFeedbackModal();
function openFeedbackModal() {
  let v = document.getElementById('fbmodal');
  if (!v) { v = document.createElement('div'); v.id = 'fbmodal'; v.className = 'modal'; document.body.appendChild(v); }
  let reporter = ''; try { reporter = localStorage.getItem('fb-reporter') || ''; } catch (e) { /* ignore */ }
  const ctx = P && location.hash.startsWith('#/project/') ? `專案 ${P.order_no} ${P.site_name}` : '';
  v.style.display = 'flex';
  const pending = [];   // 要一起送出的截圖 / 檔案
  v.innerHTML = `<div class="modal-box" style="width:min(96vw,640px)"><div class="row" style="justify-content:space-between"><b>意見回饋</b><button type="button" id="fbclose">關閉</button></div>
    <p class="muted small" style="margin:0">寫下你遇到的狀況或想要的功能，會連同目前頁面一起記錄；管理者會在「回饋」頁看到並處理。</p>
    <form id="fbform" style="display:grid;gap:8px">
      <label class="muted small">類型<br><select name="category" style="width:100%">${Object.entries(FB_CAT).map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select></label>
      <label class="muted small">內容（越具體越好：在哪一頁、做了什麼、看到什麼、預期是什麼）<br><textarea name="message" rows="5" required style="width:100%"></textarea></label>
      <div class="fb-drop" id="fbdrop"><div class="muted small">附上畫面或檔案（可多個）：<b>Win + Shift + S</b> 截圖後在這裡按 <b>Ctrl + V</b> 貼上，或把檔案拖進來，或
        <label class="link" style="cursor:pointer">選檔案<input type="file" id="fbfile" multiple accept="image/*,.pdf,.xlsx,.xls,.csv,.txt,.md,.docx,.zip" hidden></label></div>
        <div id="fbfiles" class="fb-files"></div></div>
      <div class="row"><label class="muted small">你的名字<br><input name="reporter" value="${esc(reporter)}" placeholder="方便確認細節時找你"></label>
        <span class="muted small">頁面：${esc(location.hash || '#/projects')}${ctx ? '｜' + esc(ctx) : ''}</span></div>
      <div><button class="primary">送出</button></div></form></div>`;
  v.querySelector('#fbclose').onclick = () => (v.style.display = 'none');
  v.onclick = (e) => { if (e.target === v) v.style.display = 'none'; };
  const addFiles = (list) => {
    for (const f of list) {
      if (!f || !f.size) continue;
      if (f.size > 25 * 1024 * 1024) { toast(`${f.name} 超過 25 MB`, true); continue; }
      const name = f.name || `截圖_${new Date().toISOString().slice(11, 19).replace(/:/g, '')}.png`;
      pending.push(f.name ? f : new File([f], name, { type: f.type }));
    }
    renderFiles();
  };
  const renderFiles = () => {
    const box = v.querySelector('#fbfiles');
    box.innerHTML = pending.map((f, i) => `<span class="fb-file">${f.type.startsWith('image/') ? `<img src="${URL.createObjectURL(f)}" alt="">` : '📄'} ${esc(f.name)} <small class="muted">${Math.max(1, Math.round(f.size / 1024))} KB</small> <button type="button" class="link danger" data-rm="${i}">✕</button></span>`).join('');
    box.querySelectorAll('[data-rm]').forEach((b) => (b.onclick = () => { pending.splice(+b.dataset.rm, 1); renderFiles(); }));
  };
  v.querySelector('#fbfile').onchange = (e) => { addFiles(e.target.files); e.target.value = ''; };
  v.addEventListener('paste', (e) => { const fs = [...(e.clipboardData?.files || [])]; if (fs.length) { e.preventDefault(); addFiles(fs); } });
  const drop = v.querySelector('#fbdrop');
  drop.ondragover = (e) => { e.preventDefault(); drop.classList.add('over'); };
  drop.ondragleave = () => drop.classList.remove('over');
  drop.ondrop = (e) => { e.preventDefault(); drop.classList.remove('over'); addFiles(e.dataTransfer.files); };
  v.querySelector('#fbform').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    delete f.fbfile;
    try { localStorage.setItem('fb-reporter', f.reporter || ''); } catch (err) { /* ignore */ }
    const btn = e.target.querySelector('button.primary'); btn.disabled = true; btn.textContent = '送出中…';
    try {
      const row = await api('/feedback', { method: 'POST', body: { ...f, page: location.hash || '#/projects', context: ctx || null } });
      if (pending.length) { const fd = new FormData(); pending.forEach((pf) => fd.append('files', pf, pf.name)); await api(`/feedback/${row.id}/files`, { method: 'POST', body: fd }); }
      v.style.display = 'none'; toast(`已送出（#${row.id}${pending.length ? `，附 ${pending.length} 個檔案` : ''}），謝謝回饋`);
    } catch (err) { toast(err.message, true); btn.disabled = false; btn.textContent = '送出'; }
  };
  setTimeout(() => v.querySelector('[name=message]').focus(), 50);
}
// 回饋附件：縮圖 / 連結 + 刪除
function fbFilesHtml(f, canDelete = true) {
  return (f.files || []).map((a) => `<a class="fb-att" href="/api/feedback-files/${a.id}" target="_blank" title="${esc(a.filename)}">${(a.content_type || '').startsWith('image/') ? `<img src="/api/feedback-files/${a.id}" alt="">` : '📄 ' + esc(a.filename)}</a>${canDelete ? `<button class="link danger small" data-delfile="${a.id}" title="刪除附件">✕</button>` : ''}`).join(' ');
}

async function pageFeedback(filter = '') {
  const [status, category] = filter.split(',');
  const d = await api(`/feedback?status=${status || ''}&category=${category || ''}`);
  const cnt = (k) => d.counts[k] || 0;
  $app.innerHTML = `<div class="card">
    <div class="row" style="justify-content:space-between"><h2 style="margin:0">操作者回饋</h2>
      <span><a href="/api/feedback-export.md?status=new,planned" download><button title="把「新」與「已排程」的回饋匯成 Markdown，貼給開發者處理">匯出待處理清單</button></a></span></div>
    <p class="muted small">流程：操作者用右下角「意見回饋」送出 → 管理者在這裡看、標狀態、寫備註 → 要請開發者改的，按「匯出待處理清單」把檔案內容貼給開發者 → 改好後把狀態改「已完成」，操作者就會在「更新通知」看到這一筆被修正了（修正版本會自動帶目前版本）。</p>
    <div class="tabs">${[['', '全部'], ['new', `新 ${cnt('new')}`], ['planned', `已排程 ${cnt('planned')}`], ['done', `已完成 ${cnt('done')}`], ['rejected', `不處理 ${cnt('rejected')}`]].map(([k, t]) => `<button class="${(status || '') === k ? 'active' : ''}" data-fs="${k}">${t}</button>`).join('')}
      <select id="fbcat"><option value="">全部類型</option>${Object.entries(FB_CAT).map(([k, t]) => `<option value="${k}" ${category === k ? 'selected' : ''}>${t.split('（')[0]}</option>`).join('')}</select></div>
    <div class="tablewrap"><table><tr><th>#</th><th>時間</th><th>類型</th><th>內容</th><th>附件</th><th>頁面 / 脈絡</th><th>回報人</th><th>版本</th><th>狀態</th><th>修正版本</th><th>處理備註</th><th></th></tr>
    ${d.items.map((f) => `<tr data-id="${f.id}"><td>${f.id}</td><td class="small">${fmtDate(f.created_at)}<br><span class="muted">${String(f.created_at).slice(11, 16)}</span></td>
      <td><select name="category">${Object.entries(FB_CAT).map(([k, t]) => `<option value="${k}" ${f.category === k ? 'selected' : ''}>${t.split('（')[0]}</option>`).join('')}</select></td>
      <td style="white-space:pre-wrap;min-width:260px;max-width:420px">${esc(f.message)}</td>
      <td class="fb-files" style="min-width:120px">${fbFilesHtml(f)}<label class="link small" style="cursor:pointer" title="補附件">＋<input type="file" multiple hidden data-addfile="${f.id}" accept="image/*,.pdf,.xlsx,.xls,.csv,.txt,.md,.docx,.zip"></label></td>
      <td class="small muted">${esc(f.page || '')}${f.context ? '<br>' + esc(f.context) : ''}</td><td>${esc(f.reporter || '')}</td><td class="small muted">${esc(f.version || '')}</td>
      <td><select name="status">${Object.entries(FB_STATUS).map(([k, t]) => `<option value="${k}" ${f.status === k ? 'selected' : ''}>${t}</option>`).join('')}</select></td>
      <td><input name="resolved_version" value="${esc(f.resolved_version || '')}" placeholder="改「已完成」自動帶" style="width:110px" title="哪一版修好的；會顯示在「更新通知」"></td>
      <td><input name="admin_note" value="${esc(f.admin_note || '')}" placeholder="例：改了計價頁的折數" style="min-width:160px"></td>
      <td><button class="link danger" data-del="${f.id}">✕</button></td></tr>`).join('') || '<tr><td colspan="12" class="muted">目前沒有回饋</td></tr>'}
    </table></div></div>`;
  $app.querySelectorAll('[data-fs]').forEach((b) => (b.onclick = () => pageFeedback(`${b.dataset.fs},${$app.querySelector('#fbcat').value}`)));
  $app.querySelector('#fbcat').onchange = (e) => pageFeedback(`${status || ''},${e.target.value}`);
  $app.querySelectorAll('tr[data-id]').forEach((tr) => tr.querySelectorAll('select,input:not([type=file])').forEach((i) => { i.onchange = async () => { await api('/feedback/' + tr.dataset.id, { method: 'PUT', body: rowData(tr) }); toast('已更新'); if (i.name === 'status') pageFeedback(filter); }; i.onkeydown = (e) => { if (e.key === 'Enter') i.blur(); }; }));
  $app.querySelectorAll('[data-del]').forEach((b) => (b.onclick = async () => { if (!confirm('刪除這筆回饋（含附件）？')) return; await api('/feedback/' + b.dataset.del, { method: 'DELETE' }); pageFeedback(filter); }));
  $app.querySelectorAll('[data-delfile]').forEach((b) => (b.onclick = async () => { if (!confirm('刪除這個附件？')) return; await api('/feedback-files/' + b.dataset.delfile, { method: 'DELETE' }); pageFeedback(filter); }));
  $app.querySelectorAll('[data-addfile]').forEach((i) => (i.onchange = async (e) => { const fd = new FormData(); [...e.target.files].forEach((f) => fd.append('files', f, f.name)); try { await api(`/feedback/${i.dataset.addfile}/files`, { method: 'POST', body: fd }); toast('已加入附件'); pageFeedback(filter); } catch (err) { toast(err.message, true); } }));
  window.maybeAutoTour('feedback');
}

// 更新紀錄：把 CHANGELOG.md 用最簡單的方式轉成 HTML
function mdToHtml(md) {
  const out = []; let inList = false;
  for (const raw of md.split('\n')) {
    const line = raw.trimEnd();
    const li = /^\s*[-*]\s+(.*)/.exec(line);
    if (li) { if (!inList) { out.push('<ul>'); inList = true; } out.push(`<li>${inline(li[1])}</li>`); continue; }
    if (inList) { out.push('</ul>'); inList = false; }
    if (/^### /.test(line)) out.push(`<h3>${inline(line.slice(4))}</h3>`);
    else if (/^## /.test(line)) out.push(`<h2>${inline(line.slice(3))}</h2>`);
    else if (/^# /.test(line)) out.push(`<h1>${inline(line.slice(2))}</h1>`);
    else if (line.trim()) out.push(`<p>${inline(line)}</p>`);
  }
  if (inList) out.push('</ul>');
  return out.join('');
  function inline(s) { return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>').replace(/\*\*([^*]+)\*\*/g, '<b>$1</b>'); }
}
// 更新通知看板：目前版本、每一版針對哪些回饋做了修正、處理中的回饋、完整更新紀錄
async function pageUpdates() {
  const d = await api('/updates');
  markVersionSeen(d.version);
  const catShort = (k) => (FB_CAT[k] || k).split('（')[0];
  const item = (r) => `<li><b>#${r.id}</b> <span class="tag">${catShort(r.category)}</span> ${esc(r.message)}${r.reporter ? ` <span class="muted small">（${esc(r.reporter)} 回報）</span>` : ''}${r.admin_note ? `<br><span class="small">→ ${esc(r.admin_note)}</span>` : ''}</li>`;
  $app.innerHTML = `<div class="card">
    <div class="row" style="justify-content:space-between;align-items:baseline"><h2 style="margin:0">更新通知</h2><span class="muted">目前版本 <b>v${esc(d.version)}</b></span></div>
    <p class="muted small">這裡看三件事：哪些回饋已經修好（會寫在哪一版）、哪些還在處理、每一版改了什麼。新版本上線時，上方「更新通知」會出現紅點。</p>
    <div class="tabs" id="updtabs"><button class="active" data-t="fixed">針對回饋的修正</button><button data-t="pending">處理中 ${d.pending.length}</button><button data-t="log">完整更新紀錄</button></div>
    <div id="upd-fixed">${d.resolved.length ? d.resolved.map((g) => `<h3>v${esc(g.version)} <span class="muted small">修正了 ${g.items.length} 項回饋</span></h3><ul class="fb-list">${g.items.map(item).join('')}</ul>`).join('') : '<p class="muted">還沒有標成「已完成」的回饋。管理者在「回饋」頁把狀態改成已完成，就會列在這裡。</p>'}</div>
    <div id="upd-pending" hidden>${d.pending.length ? `<ul class="fb-list">${d.pending.map((r) => `<li><b>#${r.id}</b> <span class="tag">${catShort(r.category)}</span> <span class="tag ${r.status === 'planned' ? 'ok' : ''}">${FB_STATUS[r.status]}</span> ${esc(r.message)}${r.reporter ? ` <span class="muted small">（${esc(r.reporter)}）</span>` : ''}${r.admin_note ? `<br><span class="small">→ ${esc(r.admin_note)}</span>` : ''}</li>`).join('')}</ul>` : '<p class="muted">目前沒有待處理的回饋。</p>'}</div>
    <div id="upd-log" class="md" hidden>${mdToHtml(d.changelog || '（尚無更新紀錄）')}</div></div>`;
  $app.querySelectorAll('#updtabs button').forEach((b) => (b.onclick = () => { $app.querySelectorAll('#updtabs button').forEach((x) => x.classList.toggle('active', x === b)); ['fixed', 'pending', 'log'].forEach((t) => ($app.querySelector('#upd-' + t).hidden = t !== b.dataset.t)); }));
  window.maybeAutoTour('updates');
}
// 新版本提示：版本號和上次看過的不同 → 導覽列紅點 + 提示一次
function markVersionSeen(ver) { try { localStorage.setItem('seen-version', ver); } catch (e) { /* ignore */ } document.getElementById('upddot').hidden = true; }
function checkNewVersion(ver) {
  let seen = null; try { seen = localStorage.getItem('seen-version'); } catch (e) { /* ignore */ }
  if (!seen) { markVersionSeen(ver); return; }
  if (seen !== ver) { document.getElementById('upddot').hidden = false; if (!location.hash.startsWith('#/updates')) toast(`系統已更新到 v${ver}，點「更新通知」看改了什麼`); }
}
document.getElementById('tourbtn').onclick = () => { if (!window.startTour(tourName())) toast('這一頁沒有導覽'); };

// ───────── 專案列表 ─────────
async function pageProjects() {
  await ensureMaster();
  const list = await api('/projects');
  $app.innerHTML = `
  <div class="grid2">
    <div class="card">
      <h2>新增專案 (料單)</h2>
      <form id="newp" class="row">
        <label>案場 <input name="site_name" required placeholder="例：新竹金山街"></label>
        <label>客戶 <select name="customer_id"></select></label>
        <label>業務/設計師 <input name="designer" list="designers"><datalist id="designers">${[...new Set([...(state.lookups['設計師'] || []), ...state.customers.map((c) => c.name)])].map((d) => `<option value="${esc(d)}">`).join('')}</datalist></label>
        <label>訂貨日期 <input type="date" name="order_date" value="${today()}"></label>
        <label>交貨日期 <input type="date" name="delivery_date"></label>
        <label>板厚 (mm) <span class="row" style="gap:2px">${thicknessSelect(null)}</span></label>
        <label>拉/KD <select name="joint_type">${opt(['L', 'KD', '拉'], '')}</select></label>
        <label>送貨地址 <input name="delivery_address" style="min-width:220px"></label>
        <button class="primary">建立空白專案</button>
      </form>
    </div>
    <div class="card">
      <h2>從既有 Excel 料單匯入</h2>
      <p class="muted">選擇「拆單系統 2026年6.0版」格式的 .xlsx（有「料單」分頁）。會建立新專案並保留 Excel 內手動填的封邊、備註、提醒。</p>
      <form id="imp" class="row"><input type="file" name="file" accept=".xlsx" required><button class="primary">匯入</button><span id="impmsg" class="muted"></span></form>
    </div>
  </div>
  <div class="card">
    <div class="row" style="justify-content:space-between"><h2>專案列表</h2><input id="q" placeholder="搜尋案場 / 訂單編號"></div>
    <div class="tablewrap"><table id="plist">
      <tr><th>訂單編號</th><th>案場</th><th>客戶</th><th>設計師</th><th>訂貨日</th><th>交貨日</th><th>板厚</th><th class="r">櫃體</th><th class="r">片數</th><th class="r">圖面</th><th>狀態</th><th></th></tr>
      ${list.map((p) => `<tr data-row="${esc(p.site_name)} ${esc(p.order_no)}">
        <td><a href="#/project/${p.id}">${esc(p.order_no)}</a></td><td><a href="#/project/${p.id}">${esc(p.site_name)}</a></td><td>${esc(p.customer_name || '')}</td>
        <td>${esc(p.designer || '')}</td><td>${p.order_date}</td><td>${p.delivery_date || ''}</td><td>${p.board_thickness}</td>
        <td class="r">${p.cabinet_count}</td><td class="r">${p.piece_count}</td><td class="r">${p.attachment_count}</td>
        <td><span class="pill ${p.status}">${STATUS[p.status] || p.status}</span></td>
        <td class="nowrap"><button class="link" data-export="${p.id}" title="匯出 Excel 料單">⬇ Excel</button> <button class="link danger" data-del="${p.id}">刪除</button></td></tr>`).join('') || '<tr><td colspan="12" class="muted">尚無專案</td></tr>'}
    </table></div>
  </div>`;
  $app.querySelector('select[name=customer_id]').innerHTML = customerOptions('');
  wireCustomerSelect($app.querySelector('select[name=customer_id]'), $app.querySelector('#newp [name=designer]'));
  $app.querySelector('#newp').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    f.customer_id = f.customer_id === '__new__' ? null : n0(f.customer_id); f.board_thickness = +f.board_thickness; f.delivery_date = f.delivery_date || null; f.joint_type = f.joint_type || null;
    try { const p = await api('/projects', { method: 'POST', body: f }); location.hash = `#/project/${p.id}`; } catch (err) { toast(err.message, true); }
  };
  $app.querySelector('#imp').onsubmit = async (e) => {
    e.preventDefault();
    const fd = new FormData(e.target); const msg = $app.querySelector('#impmsg');
    msg.textContent = '匯入中…';
    try {
      const r = await api('/projects/import-xlsx', { method: 'POST', body: fd });
      if (r.warnings?.length) alert('匯入提醒：\n' + r.warnings.join('\n'));
      toast(`已匯入 ${r.cabinets} 個櫃體、${r.parts} 列板材`); location.hash = `#/project/${r.project_id}`;
    } catch (err) { msg.textContent = ''; toast(err.message, true); }
  };
  $app.querySelector('#q').oninput = (e) => {
    const k = e.target.value.trim();
    $app.querySelectorAll('#plist tr[data-row]').forEach((tr) => (tr.style.display = !k || tr.dataset.row.includes(k) ? '' : 'none'));
  };
  $app.querySelectorAll('[data-del]').forEach((b) => (b.onclick = async () => {
    if (!confirm('確定刪除此專案與所有櫃體/板材/圖面？')) return;
    await api('/projects/' + b.dataset.del, { method: 'DELETE' }); toast('已刪除'); pageProjects();
  }));
  $app.querySelectorAll('[data-export]').forEach((b) => (b.onclick = () => exportXlsx(b.dataset.export)));
  window.maybeAutoTour('projects');
}

// 專案頁頂端「快速開始」：用現有資料算每一步做到哪
function quickstartCard(p) {
  const parts = p.cabinets.flatMap((c) => c.parts.filter((x) => x.name));
  const boards = parts.filter((x) => !(x.category || '').endsWith('五金'));
  const noColor = boards.filter((x) => !x.color_code).length;
  const noSize = boards.filter((x) => x.length == null || x.width == null).length;
  const drafts = p.cabinets.flatMap((c) => c.parts.filter((x) => !x.name)).length;
  const linked = p.cabinets.filter((c) => c.drawing_attachment_id).length;
  const steps = [
    { n: 1, label: `圖面 ${p.attachments.length} 份`, done: p.attachments.length > 0, tab: 'drawings', hint: '上傳設計師 PDF' },
    { n: 2, label: `櫃體 ${p.cabinets.length} 個`, done: p.cabinets.length > 0, tab: 'parts', hint: '左側新增櫃體' },
    { n: 3, label: p.attachments.length ? `對圖 ${linked}/${p.cabinets.length}` : '對圖（無圖面）', done: p.cabinets.length > 0 && (linked === p.cabinets.length || !p.attachments.length), tab: 'parts', hint: '櫃體列選圖面頁' },
    { n: 4, label: noSize ? `尺寸未填 ${noSize} 列` : '尺寸齊全', done: boards.length > 0 && noSize === 0, tab: 'parts', hint: '長/寬留空的板材' },
    { n: 5, label: noColor ? `色號未填 ${noColor} 列` : '色號齊全', done: boards.length > 0 && noColor === 0, tab: 'parts', hint: '沒色號就沒單價' },
    { n: 6, label: drafts ? `草稿列 ${drafts}` : '無草稿列', done: drafts === 0, tab: 'parts', hint: '紅框列請填名稱或刪除' },
    { n: 7, label: '檢查統計 → 匯出', done: p.status !== 'draft', tab: 'summary', hint: '看完統計把狀態改「已確認」再匯出' },
  ];
  const allDone = steps.every((s) => s.done);
  return `<div class="card compact" id="quickstart"><div class="quickstart">
    <span class="muted">快速開始${allDone ? '：全部完成 ✓' : ''}</span>
    ${steps.map((s) => `<span class="step ${s.done ? 'done' : 'todo'}" data-qs="${s.tab}" title="${esc(s.hint)}"><b>${s.done ? '✓' : s.n}</b> ${esc(s.label)}</span>`).join('')}
  </div></div>`;
}

// 匯出 Excel：用 fetch 才能把錯誤 (例如超過範本區塊上限) 顯示成提示，而不是跳到一頁 JSON
async function exportXlsx(pid) {
  toast('匯出中…');
  const res = await fetch(`/api/projects/${pid}/export-xlsx`);
  if (!res.ok) { const d = await res.json().catch(() => ({})); return toast(d.detail || res.statusText, true); }
  const blob = await res.blob();
  const cd = res.headers.get('content-disposition') || '';
  const m = /filename\*=UTF-8''([^;]+)/.exec(cd);
  const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = m ? decodeURIComponent(m[1]) : 'export.xlsx'; a.click();
  URL.revokeObjectURL(a.href);
}

// ───────── 專案詳細 ─────────
let P = null;   // current project
async function pageProject(id, tab) {
  await ensureMaster();
  state.tab = tab || 'parts';
  if (location.hash !== `#/project/${id}/${state.tab}`) { history.replaceState(null, '', `#/project/${id}/${state.tab}`); }
  P = await api('/projects/' + id);
  const p = P;
  const rev = p.revision_dates || [];
  $app.innerHTML = `
  <div class="card compact">
    <div class="row" style="justify-content:space-between;align-items:center">
      <h2 style="margin:0">${esc(p.order_no)} ─ ${esc(p.site_name)} <span class="pill ${p.status}">${STATUS[p.status]}</span>
        <span class="muted" style="font-size:13px;font-weight:400">　板厚 ${p.board_thickness}｜${p.cabinets.length} 櫃｜圖面 ${p.attachments.length} 份</span></h2>
      <span><a href="#/projects">← 專案列表</a>　<button id="exportbtn" title="以原「拆單系統 6.0 版」範本回填，含標籤列印版等分頁">匯出 Excel 料單</button>　<button class="link" id="togglehdr">表頭 ▾</button></span>
    </div>
    <form id="hdr" class="row" style="display:none;margin-top:8px">
      <label>案場 <input name="site_name" value="${esc(p.site_name)}" required></label>
      <label>客戶 <select name="customer_id">${customerOptions(p.customer_id)}</select></label>
      <label>業務/設計師 <input name="designer" list="designers" value="${esc(p.designer || '')}"><datalist id="designers">${(state.lookups['設計師'] || []).map((d) => `<option value="${esc(d)}">`).join('')}</datalist></label>
      <label>訂貨日期 <input type="date" name="order_date" value="${p.order_date}"></label>
      <label>交貨日期 <input type="date" name="delivery_date" value="${p.delivery_date || ''}"></label>
      <label>拉/KD <select name="joint_type">${opt(['L', 'KD', '拉'], p.joint_type || '')}</select></label>
      <label>板厚 (mm) <span class="row" style="gap:2px">${thicknessSelect(p.board_thickness)}</span></label>
      <label>狀態 <select name="status">${Object.entries(STATUS).map(([k, v]) => `<option value="${k}" ${k == p.status ? 'selected' : ''}>${v}</option>`).join('')}</select></label>
      <label>送貨地址 <input name="delivery_address" value="${esc(p.delivery_address || '')}" style="min-width:240px"></label>
      <label>1修改日期 <input type="date" name="rev1" value="${rev[0] || ''}"></label>
      <label>2修改日期 <input type="date" name="rev2" value="${rev[1] || ''}"></label>
      <label>3修改日期 <input type="date" name="rev3" value="${rev[2] || ''}"></label>
      <label>備註 <input name="note" value="${esc(p.note || '')}" style="min-width:220px"></label>
      <button class="primary">儲存表頭</button>
    </form>
  </div>
  ${quickstartCard(p)}
  <div class="tabs">
    ${[['parts', '料單'], ['drawings', `圖面 (${p.attachments.length})`], ['summary', '統計'], ['quote', '計價/報價'], ['labels', '標籤列印'], ['serials', '流水號/掃描'], ['material', '叫料計算'], ['partslist', '零件單']]
      .map(([k, v]) => `<button class="${state.tab == k ? 'active' : ''}" data-tab="${k}">${v}</button>`).join('')}
  </div>
  <div id="tabbody"></div>
  <div id="viewer" class="modal" style="display:none"></div>`;
  $app.querySelectorAll('[data-qs]').forEach((s) => (s.onclick = () => { location.hash = `#/project/${id}/${s.dataset.qs}`; }));
  $app.querySelector('#exportbtn').onclick = () => exportXlsx(id);
  wireCustomerSelect($app.querySelector('#hdr select[name=customer_id]'), $app.querySelector('#hdr [name=designer]'));
  $app.querySelector('#togglehdr').onclick = () => { const f = $app.querySelector('#hdr'); f.style.display = f.style.display === 'none' ? 'flex' : 'none'; };
  $app.querySelector('#hdr').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    f.customer_id = f.customer_id === '__new__' ? null : n0(f.customer_id); f.board_thickness = +f.board_thickness; f.delivery_date = f.delivery_date || null; f.joint_type = f.joint_type || null;
    f.revision_dates = [f.rev1, f.rev2, f.rev3].filter(Boolean);
    try { await api('/projects/' + id, { method: 'PUT', body: f }); toast('已儲存'); pageProject(id, state.tab); }
    catch (err) { toast(err.message, true); }
  };
  $app.querySelectorAll('[data-tab]').forEach((b) => (b.onclick = () => { location.hash = `#/project/${id}/${b.dataset.tab}`; }));
  const body = document.getElementById('tabbody');
  await ({ parts: renderParts, drawings: renderDrawings, summary: renderSummary, quote: renderQuote, labels: renderLabels, serials: renderSerials, material: renderMaterial, partslist: renderPartsList })[state.tab](body, p);
  window.maybeAutoTour('project-' + state.tab);
}

// ───────── 料單 ─────────
function renderParts(body, p) {
  const cats = Object.keys(state.catalog);
  body.innerHTML = `
  <div class="split">
    <aside class="nav card compact">
      <div class="row" style="justify-content:space-between"><b>櫃體 (${p.cabinets.length})</b>
        <span><button class="link" id="expall">展開</button><button class="link" id="colall">收合</button></span></div>
      <ul>${p.cabinets.map((cb) => `<li><a href="#cab-${cb.id}" data-nav="${cb.id}"><span class="no">${cb.cabinet_no}</span> ${esc(cb.name)} <span class="muted">${cb.parts.filter((x) => !(x.category || '').endsWith('五金')).reduce((a, x) => a + x.qty, 0)}片</span></a></li>`).join('')}</ul>
      <form id="newcab" class="newcab">
        <b>新增櫃體</b>
        <input name="name" required placeholder="櫃體名稱 (例：玄關收納疊櫃)" list="cabnames"><datalist id="cabnames">${[...new Set(p.cabinets.map((c) => c.name))].map((n) => `<option value="${esc(n)}">`).join('')}</datalist>
        <div class="row"><label>櫃高 <input class="num" name="height" type="number" step="0.1"></label><label>櫃深 <input class="num" name="depth" type="number" step="0.1"></label><label>櫃寬 <input class="num" name="width" type="number" step="0.1"></label></div>
        <div class="row"><label>色號 <input class="num" name="color_code" list="colors"></label><label>櫃號 <input class="sm" name="cabinet_no" type="number" placeholder="自動"></label><label>批次 <input class="sm" name="batch" type="number" value="1"></label></div>
        <label class="chk"><input type="checkbox" name="gen" checked> 自動產生桶身/內部/門板標準板件</label>
        <button class="primary">新增櫃體</button>
      </form>
    </aside>
    <div class="main">
      ${p.cabinets.map((cb) => cabinetCard(cb, cats, p)).join('') || '<div class="card muted">尚無櫃體：左側新增，或回專案列表用 Excel 匯入。</div>'}
    </div>
  </div>${colorDatalist()}${nameDatalist()}`;

  body.querySelector('#expall').onclick = () => { state.collapsed.clear(); renderParts(body, p); };
  body.querySelector('#colall').onclick = () => { p.cabinets.forEach((c) => state.collapsed.add(c.id)); renderParts(body, p); };
  body.querySelectorAll('[data-nav]').forEach((a) => (a.onclick = (e) => { e.preventDefault(); state.collapsed.delete(+a.dataset.nav); renderParts(body, p); document.getElementById('cab-' + a.dataset.nav)?.scrollIntoView({ behavior: 'smooth', block: 'start' }); }));
  body.querySelector('#newcab').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    try {
      await api(`/projects/${p.id}/cabinets`, { method: 'POST', body: { name: f.name.trim(), cabinet_no: n0(f.cabinet_no), height: n0(f.height), depth: n0(f.depth), width: n0(f.width), batch: +f.batch || 1, color_code: f.color_code || null, generate_default_parts: !!f.gen } });
      toast('已新增櫃體'); pageProject(p.id, 'parts');
    } catch (err) { toast(err.message, true); }
  };
  body.querySelectorAll('[data-collapse]').forEach((b) => (b.onclick = () => { const id = +b.dataset.collapse; state.collapsed.has(id) ? state.collapsed.delete(id) : state.collapsed.add(id); renderParts(body, p); }));
  p.cabinets.forEach((cb) => wireCabinet(body, p, cb));
}

// 只重畫一個櫃體卡片 (儲存一格後不整頁重載，游標與捲動位置不跑掉)
async function refreshCabinet(body, p, cabId) {
  const fresh = await api('/cabinets/' + cabId);
  const i = p.cabinets.findIndex((c) => c.id === cabId);
  if (i < 0) return;
  p.cabinets[i] = fresh;
  const old = document.getElementById('cab-' + cabId);
  if (!old) return;
  const tmp = document.createElement('div');
  tmp.innerHTML = cabinetCard(fresh, Object.keys(state.catalog), p);
  old.replaceWith(tmp.firstElementChild);
  wireCabinet(body, p, fresh);
  const nav = body.querySelector(`[data-nav="${cabId}"]`);
  if (nav) nav.innerHTML = `<span class="no">${fresh.cabinet_no}</span> ${esc(fresh.name)} <span class="muted">${fresh.parts.filter((x) => x.name && !(x.category || '').endsWith('五金')).reduce((a, x) => a + x.qty, 0)}片</span>`;
}

function wireCabinet(body, p, cb) {
  const card = document.getElementById('cab-' + cb.id);
  if (!card) return;
  const q = (sel) => card.querySelectorAll(sel);
  const form = card.querySelector('form.cabform');
  form.onsubmit = async (e) => {
    e.preventDefault();
    const d = Object.fromEntries(new FormData(form));
    const [aid, pg] = (d.drawing || '').split(':');
    try {
      await api('/cabinets/' + cb.id, { method: 'PUT', body: { name: d.name.trim(), cabinet_no: n0(d.cabinet_no), height: n0(d.height), depth: n0(d.depth), width: n0(d.width), batch: +d.batch || 1, note: d.note || null, color_code: d.color_code || null, drawing_attachment_id: n0(aid), drawing_page: n0(pg), drawing_label: d.drawing_label || null, generate_default_parts: false } });
      toast('櫃體已更新'); pageProject(p.id, 'parts');
    } catch (err) { toast(err.message, true); }
  };
  q('[data-dup]').forEach((b) => (b.onclick = async () => { try { const n = await api(`/cabinets/${cb.id}/duplicate`, { method: 'POST' }); toast(`已複製為櫃號 ${n.cabinet_no}`); pageProject(p.id, 'parts'); } catch (err) { toast(err.message, true); } }));
  q('[data-applycolor]').forEach((b) => (b.onclick = async () => {
    const code = form.querySelector('[name=color_code]').value.trim();
    if (!code) return toast('請先填櫃體色號', true);
    const skip = !confirm(`把色號 ${code} 套用到此櫃全部板材？\n（按「取消」則只套到板材，背板/抽底維持不變）`) ;
    try { await api(`/cabinets/${cb.id}/apply-color`, { method: 'POST', body: { color_code: code, only_empty: false, skip_backboard: skip } }); refreshCabinet(body, p, cb.id); }
    catch (err) { toast(err.message, true); }
  }));
  q('[data-view]').forEach((b) => (b.onclick = () => { const [aid, pg] = b.dataset.view.split(':'); openViewer(+aid, +pg || 1); }));
  q('[data-delcab]').forEach((b) => (b.onclick = async () => { if (!confirm(`刪除櫃號 ${cb.cabinet_no}「${cb.name}」與其全部板材？`)) return; await api('/cabinets/' + cb.id, { method: 'DELETE' }); toast('已刪除'); pageProject(p.id, 'parts'); }));
  q('[data-addpart]').forEach((b) => (b.onclick = async () => {
    try {
      const r = await api(`/cabinets/${cb.id}/parts`, { method: 'POST', body: { name: '', qty: 1, category: b.dataset.cat || null } });
      await refreshCabinet(body, p, cb.id); document.querySelector(`tr[data-part="${r.id}"] input[name=name]`)?.focus();
    } catch (err) { toast(err.message, true); }
  }));
  q('[data-delpart]').forEach((b) => (b.onclick = async () => {
    const x = cb.parts.find((y) => y.id === +b.dataset.delpart);
    if (x?.name && !confirm(`刪除 ${x.part_no}「${x.name}」？`)) return;
    await api('/parts/' + b.dataset.delpart, { method: 'DELETE' }); refreshCabinet(body, p, cb.id);
  }));
  q('[data-reset]').forEach((b) => (b.onclick = async () => { await api(`/parts/${b.dataset.reset}/reset-auto`, { method: 'POST' }); refreshCabinet(body, p, cb.id); }));
  q('tr[data-part]').forEach((tr) => {
    tr.querySelectorAll('input,select').forEach((inp) => {
      inp.onchange = async () => {
        if (tr.dataset.saving) return;           // 上一格還在存：這次變更會在重畫後要求再改一次
        const part = cb.parts.find((y) => y.id === +tr.dataset.part);   // 每次都讀最新的 manual_fields
        const g = (n) => tr.querySelector(`[name=${n}]`);
        const manual = new Set(part.manual_fields || []);
        if (AUTO_FIELDS.includes(inp.name)) manual.add(inp.name);
        const data = {
          category: g('category').value || null, name: g('name').value.trim(), length: n0(g('length').value), width: n0(g('width').value),
          thickness: n0(g('thickness').value), qty: Math.max(0, +g('qty').value || 0), color_code: g('color_code').value.trim() || null,
          remark: g('remark').value || null, status_code: g('status_code').value || 'A', manual_fields: [...manual],
        };
        AUTO_FIELDS.forEach((f) => (data[f] = g(f).value));
        tr.dataset.saving = '1';
        try {
          await api('/parts/' + part.id, { method: 'PUT', body: data });
          const focusName = inp.name;
          await refreshCabinet(body, p, cb.id);
          const next = nextInput(document.querySelector(`tr[data-part="${part.id}"]`), focusName); next?.focus({ preventScroll: true }); next?.select?.();
        } catch (err) { delete tr.dataset.saving; toast(err.message, true); }
      };
      inp.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); inp.blur(); } };
    });
  });
}
const ORDER = ['name', 'category', 'length', 'edge_l', 'width', 'edge_w', 'thickness', 'qty', 'color_code', 'mark_p', 'mark_q', 'mark_r', 'remark', 'reminder', 'status_code'];
function nextInput(tr, name) { if (!tr) return null; const i = ORDER.indexOf(name); return i >= 0 && i + 1 < ORDER.length ? tr.querySelector(`[name=${ORDER[i + 1]}]`) : null; }
function findPart(p, id) { for (const cb of p.cabinets) for (const x of cb.parts) if (x.id === id) return x; return null; }

function cabinetCard(cb, cats, p) {
  const statusOpts = (cur) => state.lookups['狀態'].map((s) => `<option value="${s.code}" ${s.code == cur ? 'selected' : ''}>${s.code} ${esc(s.name)}</option>`).join('');
  const pieces = cb.parts.filter((x) => x.name && !(x.category || '').endsWith('五金')).reduce((a, x) => a + x.qty, 0);
  const cai = cb.parts.filter((x) => x.name).reduce((a, x) => a + (+x.area_cai || 0), 0);
  const collapsed = state.collapsed.has(cb.id);
  const drawOpts = `<option value="">-</option>` + p.attachments.flatMap((a) => Array.from({ length: a.page_count || 1 }, (_, i) => i + 1).map((pg) => `<option value="${a.id}:${pg}" ${a.id == cb.drawing_attachment_id && pg == cb.drawing_page ? 'selected' : ''}>${esc(a.filename.slice(0, 18))} p${pg}</option>`)).join('');
  const manualCell = (x, f, inner) => `<td class="auto ${(x.manual_fields || []).includes(f) ? 'manual' : ''}">${inner}</td>`;
  const edgeSel = (x, f) => manualCell(x, f, `<select name="${f}" class="edge">${opt(['AA', 'A'], x[f] || '')}</select>`);
  const txt = (x, f, w = 70) => manualCell(x, f, `<input name="${f}" value="${esc(x[f] || '')}" style="width:${w}px;min-width:${w}px">`);
  return `<div class="card cab ${collapsed ? 'collapsed' : ''}" id="cab-${cb.id}">
    <form class="cabform cab-head" data-id="${cb.id}">
      <button type="button" class="link" data-collapse="${cb.id}" title="展開/收合">${collapsed ? '▸' : '▾'}</button>
      <span class="title">櫃號 ${cb.cabinet_no}</span>
      <label>櫃體名稱 <input name="name" value="${esc(cb.name)}" style="min-width:150px"></label>
      <label>櫃號 <input class="sm" name="cabinet_no" type="number" value="${cb.cabinet_no}"></label>
      <label>櫃高 <input class="num" name="height" type="number" step="0.1" value="${cb.height ?? ''}"></label>
      <label>櫃深 <input class="num" name="depth" type="number" step="0.1" value="${cb.depth ?? ''}"></label>
      <label>櫃寬 <input class="num" name="width" type="number" step="0.1" value="${cb.width ?? ''}"></label>
      <label>批次 <input class="sm" name="batch" type="number" value="${cb.batch}"></label>
      <label>櫃體色號 <input class="num" name="color_code" list="colors" value="${esc(cb.color_code || '')}"></label>
      <button type="button" class="link" data-applycolor="${cb.id}" title="把櫃體色號套用到全部板材">套用色號</button>
      <label>圖面頁 <select name="drawing">${drawOpts}</select></label>
      <label>圖上編號 <input class="sm" name="drawing_label" value="${esc(cb.drawing_label || '')}" placeholder="①"></label>
      ${cb.drawing_attachment_id ? `<button type="button" class="link" data-view="${cb.drawing_attachment_id}:${cb.drawing_page || 1}">看圖</button>` : ''}
      <label>備註 <input name="note" value="${esc(cb.note || '')}"></label>
      <span class="muted">片數 ${pieces}｜才數 ${cai.toFixed(2)}</span>
      <button>更新</button>
      <button type="button" class="link" data-dup="${cb.id}" title="複製此櫃體與全部板材">複製櫃體</button>
      <button type="button" class="link danger" data-delcab="${cb.id}">刪除</button>
    </form>
    ${collapsed ? '' : `<div class="tablewrap"><table class="parts">
      <tr><th>編號</th><th>板材名稱</th><th>類別</th><th>長(同紋)</th><th>封邊</th><th>寬</th><th>封邊</th><th>厚</th><th>數量</th><th>色號</th><th>色號名稱 / 板商 / 封邊色號</th>
          <th>備註1</th><th>備註2</th><th>備註3</th><th>備註4</th><th>提醒</th><th class="r">才數</th><th class="r">金額</th><th>狀態</th><th></th></tr>
      ${cb.parts.map((x) => `<tr data-part="${x.id}" class="${(x.category || '').endsWith('五金') ? 'hw' : ''} ${x.name ? '' : 'draft'}">
        <td class="muted">${x.part_no}</td>
        <td><input name="name" list="partnames" value="${esc(x.name)}" style="min-width:130px" placeholder="請填板材名稱 (未填不列入)"></td>
        <td><select name="category">${opt(cats, x.category)}</select></td>
        <td><input class="num" name="length" type="number" step="0.1" value="${x.length ?? ''}"></td>
        ${edgeSel(x, 'edge_l')}
        <td><input class="num" name="width" type="number" step="0.1" value="${x.width ?? ''}"></td>
        ${edgeSel(x, 'edge_w')}
        <td><input class="sm" name="thickness" type="number" step="0.1" value="${x.thickness ?? ''}"></td>
        <td><input class="sm" name="qty" type="number" value="${x.qty}"></td>
        <td><input class="num" name="color_code" value="${esc(x.color_code || '')}" list="colors"></td>
        <td class="auto small">${esc(x.color_name || '')}${x.board_vendor ? ' / ' + esc(x.board_vendor) : ''}${x.edge_code ? ' / ' + esc(x.edge_code) : ''}</td>
        ${txt(x, 'mark_p', 90)}${txt(x, 'mark_q', 80)}${txt(x, 'mark_r', 60)}
        <td><input name="remark" value="${esc(x.remark || '')}" style="width:90px;min-width:90px"></td>
        ${txt(x, 'reminder', 100)}
        <td class="auto r">${num(x.area_cai)}</td><td class="auto r">${num(x.amount)}</td>
        <td><select name="status_code">${statusOpts(x.status_code)}</select></td>
        <td class="nowrap">${(x.manual_fields || []).length ? `<button type="button" class="link" data-reset="${x.id}" title="清除手動覆寫，恢復自動值">↺</button>` : ''}<button type="button" class="link danger" data-delpart="${x.id}">✕</button></td>
      </tr>`).join('')}
    </table></div>
    <div class="row" style="margin-top:6px">
      <button type="button" class="link" data-addpart="${cb.id}">＋ 板材</button>
      ${['桶身', '內部', '外部', '抽屜', '內部五金', '外部五金', '其它五金'].map((c) => `<button type="button" class="link small" data-addpart="${cb.id}" data-cat="${c}">＋${c}</button>`).join('')}
      <span class="muted small">　藍底 = 自動計算；黃底 = 手動覆寫 (↺ 可恢復)；紅框 = 名稱未填的草稿列 (不列入報表)。欄位改完按 Enter 或點別處即儲存。</span>
    </div>`}
  </div>`;
}

// ───────── 圖面檢視器 ─────────
function openViewer(aid, page) {
  const a = P.attachments.find((x) => x.id === aid); if (!a) return;
  const v = document.getElementById('viewer'); v.style.display = 'flex';
  const draw = () => {
    v.innerHTML = `<div class="modal-box">
      <div class="row" style="justify-content:space-between"><b>${esc(a.filename)}　第 ${page} / ${a.page_count} 頁</b>
        <span><button id="vprev">◀</button> <button id="vnext">▶</button> <a href="/api/attachments/${aid}/pages/${page}.png?dpi=200" target="_blank"><button>原尺寸開新視窗</button></a> <a href="/api/attachments/${aid}/file" target="_blank"><button>下載 PDF</button></a> <button id="vclose">關閉</button></span></div>
      <div class="imgwrap"><img src="/api/attachments/${aid}/pages/${page}.png?dpi=110" alt="page ${page}"></div>
      <div class="muted small">本頁對應櫃體：${P.cabinets.filter((c) => c.drawing_attachment_id === aid && c.drawing_page === page).map((c) => `${c.drawing_label || ''}櫃號${c.cabinet_no} ${esc(c.name)}`).join('、') || '（尚未指定，請在櫃體列選「圖面頁」）'}</div>
    </div>`;
    v.querySelector('#vclose').onclick = () => (v.style.display = 'none');
    v.querySelector('#vprev').onclick = () => { if (page > 1) { page--; draw(); } };
    v.querySelector('#vnext').onclick = () => { if (page < (a.page_count || 1)) { page++; draw(); } };
    v.onclick = (e) => { if (e.target === v) v.style.display = 'none'; };
  };
  draw();
}

// ───────── 圖面 / 附件 ─────────
function renderDrawings(body, p) {
  body.innerHTML = `<div class="card">
    <h3>上傳圖面 / 附件</h3>
    <form id="up" class="row"><input type="file" name="file" accept=".pdf,.png,.jpg,.jpeg,.webp" multiple required>
      <label>類型 <select name="kind">${opt(['drawing', 'photo', 'other'], 'drawing', false)}</select></label>
      <label>備註 <input name="note" placeholder="例：設計師 10/16 版"></label><button class="primary">上傳</button><span id="upmsg" class="muted"></span></form>
    <p class="muted small">建議：設計師的 PDF 整份上傳（一頁一區域），再到「料單」的櫃體列把每個櫃體對到「圖面頁」並填圖上編號 ①②③，拆單時點「看圖」即可對照。</p>
  </div>
  ${p.attachments.map((a) => `<div class="card">
    <div class="row" style="justify-content:space-between">
      <b>${esc(a.filename)}</b><span class="muted">${(a.size / 1024 / 1024).toFixed(2)} MB｜${a.page_count || 1} 頁｜${a.kind}｜${new Date(a.uploaded_at).toLocaleString('zh-TW')}</span>
      <span><input data-note="${a.id}" value="${esc(a.note || '')}" placeholder="備註"> <a href="/api/attachments/${a.id}/file" target="_blank"><button>下載</button></a> <button class="danger" data-delatt="${a.id}">刪除</button></span>
    </div>
    <div class="thumbs">${Array.from({ length: a.page_count || 1 }, (_, i) => i + 1).map((pg) => `<figure data-view="${a.id}:${pg}"><img loading="lazy" src="/api/attachments/${a.id}/pages/${pg}.png?dpi=40"><figcaption>第 ${pg} 頁 ${p.cabinets.filter((c) => c.drawing_attachment_id === a.id && c.drawing_page === pg).map((c) => c.drawing_label || `#${c.cabinet_no}`).join(' ')}</figcaption></figure>`).join('')}</div>
  </div>`).join('') || '<div class="card muted">尚未上傳圖面。</div>'}`;
  body.querySelector('#up').onsubmit = async (e) => {
    e.preventDefault();
    const files = e.target.file.files; const msg = body.querySelector('#upmsg');
    let ok = 0, fail = 0;
    for (const f of files) {
      msg.textContent = `上傳 ${f.name}…`;
      const fd = new FormData(); fd.append('file', f);
      try { await api(`/projects/${p.id}/attachments?kind=${e.target.kind.value}&note=${encodeURIComponent(e.target.note.value)}`, { method: 'POST', body: fd }); ok++; }
      catch (err) { fail++; toast(`${f.name}：${err.message}`, true); }
    }
    if (ok) toast(`上傳完成 ${ok} 個${fail ? `，失敗 ${fail} 個` : ''}`);
    if (ok) pageProject(p.id, 'drawings'); else msg.textContent = '';
  };
  body.querySelectorAll('[data-view]').forEach((f) => (f.onclick = () => { const [aid, pg] = f.dataset.view.split(':'); openViewer(+aid, +pg); }));
  body.querySelectorAll('[data-note]').forEach((i) => (i.onchange = async () => { await api('/attachments/' + i.dataset.note, { method: 'PUT', body: { note: i.value } }); toast('已儲存'); }));
  body.querySelectorAll('[data-delatt]').forEach((b) => (b.onclick = async () => { if (!confirm('刪除此圖面？')) return; await api('/attachments/' + b.dataset.delatt, { method: 'DELETE' }); pageProject(p.id, 'drawings'); }));
}

// ───────── 報表 ─────────
async function renderSummary(body, p) {
  const s = await api(`/projects/${p.id}/summary`);
  body.innerHTML = `<div class="card"><h3>料單統計</h3>
    <div class="kpi"><div>板材總片數<b>${s.total_pieces}</b></div><div>板材總才數<b>${num(s.total_cai)}</b></div><div>板材金額 (未稅)<b>${num(s.total_amount)}</b></div><div>櫃體數<b>${s.cabinets.length}</b></div></div>
    <br><table><tr><th>櫃號</th><th>櫃體名稱</th><th class="r">板材片數</th><th class="r">板材才數</th><th class="r">金額</th></tr>
    ${s.cabinets.map((c) => `<tr><td>${c.cabinet_no}</td><td>${esc(c.name)}</td><td class="r">${c.pieces}</td><td class="r">${num(c.cai)}</td><td class="r">${num(c.amount)}</td></tr>`).join('')}
    </table></div>`;
}

// 開新視窗列印 (報價單 / 零件單 / 對帳單 / 計價清單)
function printHtml(title, inner) {
  const w = window.open('', '_blank');
  w.document.write(`<!doctype html><html lang="zh-Hant"><head><meta charset="utf-8"><title>${esc(title)}</title>
  <style>body{font:13px/1.5 "Noto Sans TC","Microsoft JhengHei",sans-serif;margin:24px;color:#111}h1{font-size:20px;margin:0 0 4px;text-align:center}h2{font-size:15px;margin:14px 0 6px}
  table{border-collapse:collapse;width:100%;margin:6px 0}th,td{border:1px solid #333;padding:3px 6px;font-size:12px}th{background:#eee}.r{text-align:right}.meta{display:grid;grid-template-columns:1fr 1fr;gap:2px 20px;margin:8px 0}.muted{color:#555}
  .tot td{font-weight:700}.sign{margin-top:28px;display:flex;justify-content:space-between}.pre{white-space:pre-wrap}@media print{button{display:none}}</style></head>
  <body>${inner}<p style="text-align:center;margin-top:20px"><button onclick="window.print()">列印</button></p></body></html>`);
  w.document.close();
}
const fmtDate = (d) => (d ? String(d).slice(0, 10) : '');

async function renderQuote(body, p) {
  const [q, procs, settings] = await Promise.all([api(`/projects/${p.id}/quote`), api('/master/process-prices'), api('/settings')]);
  const pr = q.project;
  const meta = pr.quote_meta || {};
  body.innerHTML = `
  <div class="card compact">
    <div class="row" style="justify-content:space-between"><h3 style="margin:0">計價清單</h3>
      <span><button id="printlist">列印計價清單</button> <button class="primary" id="printquote">列印報價單</button></span></div>
    <div class="row"><span>訂單編號：<b>${esc(pr.order_no)}</b></span><span>客戶：${esc(pr.customer_code || '')} ${esc(pr.customer_name || '')}</span><span>案場：${esc(pr.site_name)}</span><span>訂單日期：${pr.order_date}</span><span>交貨日期：${pr.delivery_date || ''}</span></div>
  </div>
  <div class="grid2">
    <div class="card compact"><h3>計價設定</h3>
      <form id="qs" class="row">
        <label>板材折數 <input class="num" name="board_discount" type="number" step="0.001" min="0" max="1" value="${pr.board_discount ?? ''}" placeholder="${pr.customer_board_discount ?? '1 (無)'}"></label>
        <span class="muted small">空白＝用客戶設定（${pr.customer_board_discount ?? '未設定'}）</span>
        <label>運費 <input class="num" name="freight" type="number" value="${+pr.freight || 0}"></label>
        <label>安裝 <input class="num" name="install" type="number" value="${+pr.install || 0}" ${pr.install_auto ? 'disabled' : ''}></label>
        <label class="chk"><input type="checkbox" name="install_auto" ${pr.install_auto ? 'checked' : ''} ${pr.customer_install_discount ? '' : 'disabled'}> 安裝＝折後板材 × 客戶安裝折數 ${pr.customer_install_discount ? `(${pr.customer_install_discount})` : '(客戶未設定)'}</label>
        <button class="primary">儲存並重算</button>
      </form>
    </div>
    <div class="card compact"><h3>報價單資料</h3>
      <form id="qm" class="row">
        ${[['design_company', '設計公司'], ['contact', '聯絡人'], ['phone', '聯絡電話'], ['work_type', '施工類別'], ['site_address', '施工地址'], ['start_date', '預計進場日期']].map(([k, v]) => `<label>${v} <input name="${k}" value="${esc(meta[k] || '')}" ${k === 'start_date' ? 'type="date"' : ''}></label>`).join('')}
        <label>有效天數 <input class="sm" name="valid_days" type="number" value="${meta.valid_days || 15}"></label>
        <button>儲存</button>
      </form>
    </div>
  </div>
  <div class="card compact">
    <div class="row" style="justify-content:space-between"><h3 style="margin:0">加工費 / 額外費用</h3>
      <span><button id="feesuggest" title="依料單備註 (斜把/打型/Z把/崁把手) 自動帶入">依料單備註帶入</button></span></div>
    <div class="tablewrap"><table class="edit">
      <tr><th>項目</th><th>單位</th><th class="r">數量</th><th class="r">單價</th><th class="r">金額</th><th>備註</th><th></th></tr>
      <tr class="newrow"><td><input name="name" list="proclist" placeholder="選牌價項目或自填" style="min-width:220px"><datalist id="proclist">${procs.map((x) => `<option value="${esc(x.name)}">${esc(x.kind)}｜${esc(x.unit || '')}｜${num(x.price)}</option>`).join('')}</datalist></td>
        <td><input name="unit" class="sm"></td><td><input name="qty" type="number" step="0.01" class="num" value="1"></td><td><input name="unit_price" type="number" step="0.01" class="num"></td><td></td><td><input name="note"></td><td><button class="primary small" id="feeadd">新增</button></td></tr>
      ${q.fees.map((f) => `<tr data-fee="${f.id}"><td><input name="name" value="${esc(f.name)}" style="min-width:220px"></td><td><input name="unit" class="sm" value="${esc(f.unit || '')}"></td>
        <td><input name="qty" type="number" step="0.01" class="num" value="${+f.qty}"></td><td><input name="unit_price" type="number" step="0.01" class="num" value="${+f.unit_price}"></td>
        <td class="r auto">${num(f.amount)}</td><td><input name="note" value="${esc(f.note || '')}"></td><td><button class="link danger" data-feedel="${f.id}">✕</button></td></tr>`).join('') || '<tr><td colspan="7" class="muted">尚無加工費。可從「基礎資料 → 加工牌價」維護項目與單價。</td></tr>'}
    </table></div>
  </div>
  <div class="card compact"><h3>板材明細</h3>
    <div class="tablewrap"><table><tr><th>項次</th><th>櫃號</th><th>項目</th><th>色號</th><th>顏色</th><th class="r">長</th><th>封邊</th><th class="r">寬</th><th>封邊</th><th class="r">板厚</th><th class="r">數量</th><th class="r">才數</th><th>單位</th><th class="r">計價</th><th class="r">金額</th><th>備註</th></tr>
    ${q.lines.map((l) => `<tr><td>${l.part_no}</td><td>${l.cabinet_no} ${esc(l.cabinet_name)}</td><td>${esc(l.name)}</td><td>${esc(l.color_code || '')}</td><td>${esc(l.color_name || '')}</td><td class="r">${num(l.length)}</td><td>${esc(l.edge_l)}</td><td class="r">${num(l.width)}</td><td>${esc(l.edge_w)}</td><td class="r">${num(l.thickness)}</td><td class="r">${l.qty}</td><td class="r">${num(l.cai)}</td><td>${l.unit}</td><td class="r">${num(l.unit_price)}</td><td class="r">${num(l.amount)}</td><td>${esc(l.marks.filter(Boolean).join(' / '))}</td></tr>`).join('')}
    </table></div></div>
  <div class="card compact"><div class="kpi">
    <div>板材牌價小計<b>${num(q.subtotal)}</b></div><div>折數 <span class="muted small">(${esc(q.discount_source)})</span><b>${+q.discount}</b></div><div>折後板材<b>${num(q.boards_net)}</b></div>
    <div>加工費<b>${num(q.fees_total)}</b></div><div>安裝${q.install_auto ? ' <span class="muted small">(自動)</span>' : ''}<b>${num(q.install)}</b></div><div>運費<b>${num(q.freight)}</b></div>
    <div>未稅合計<b>${num(q.taxable)}</b></div><div>稅金 5%<b>${num(q.tax)}</b></div><div>總金額<b>${num(q.total)}</b></div></div></div>`;

  const saveSettings = async (extraMeta) => {
    const f = Object.fromEntries(new FormData(body.querySelector('#qs')));
    const m = Object.fromEntries(new FormData(body.querySelector('#qm')));
    await api(`/projects/${p.id}/quote-settings`, { method: 'PUT', body: { freight: +f.freight || 0, install: +f.install || 0, install_auto: !!f.install_auto, board_discount: n0(f.board_discount), quote_meta: { ...meta, ...m, ...extraMeta } } });
  };
  body.querySelector('#qs').onsubmit = async (e) => { e.preventDefault(); try { await saveSettings(); toast('已重算'); renderQuote(body, p); } catch (err) { toast(err.message, true); } };
  body.querySelector('#qs [name=install_auto]').onchange = (e) => { body.querySelector('#qs [name=install]').disabled = e.target.checked; };
  body.querySelector('#qm').onsubmit = async (e) => { e.preventDefault(); try { await saveSettings(); toast('已儲存'); } catch (err) { toast(err.message, true); } };
  body.querySelector('#feeadd').onclick = async (e) => {
    e.preventDefault();
    const tr = body.querySelector('tr.newrow'); const d = rowData(tr);
    if (!d.name) return toast('請填項目', true);
    try { await api(`/projects/${p.id}/fees`, { method: 'POST', body: { name: d.name, unit: d.unit, qty: d.qty ?? 1, unit_price: d.unit_price ?? 0, note: d.note } }); renderQuote(body, p); } catch (err) { toast(err.message, true); }
  };
  // 選了牌價項目 → 自動帶單位與單價
  body.querySelector('tr.newrow [name=name]').onchange = (e) => { const x = procs.find((y) => y.name === e.target.value); if (x) { body.querySelector('tr.newrow [name=unit]').value = x.unit || ''; body.querySelector('tr.newrow [name=unit_price]').value = x.price ?? ''; } };
  body.querySelector('#feesuggest').onclick = async () => { const r = await api(`/projects/${p.id}/fees/suggest`, { method: 'POST' }); toast(r.added.length ? `帶入 ${r.added.length} 項，請核對數量` : '料單備註裡沒有可帶入的加工項目（或已存在）'); if (r.added.length) renderQuote(body, p); };
  body.querySelectorAll('tr[data-fee]').forEach((tr) => {
    tr.querySelectorAll('input').forEach((i) => { i.onchange = async () => { const d = rowData(tr); try { await api('/fees/' + tr.dataset.fee, { method: 'PUT', body: { name: d.name, unit: d.unit, qty: d.qty ?? 1, unit_price: d.unit_price ?? 0, note: d.note } }); renderQuote(body, p); } catch (err) { toast(err.message, true); } }; i.onkeydown = (e) => { if (e.key === 'Enter') i.blur(); }; });
  });
  body.querySelectorAll('[data-feedel]').forEach((b) => (b.onclick = async () => { await api('/fees/' + b.dataset.feedel, { method: 'DELETE' }); renderQuote(body, p); }));

  body.querySelector('#printlist').onclick = () => printHtml(`計價清單 ${pr.order_no}`, `<h1>計價清單</h1>
    <div class="meta"><div>訂單編號：${esc(pr.order_no)}</div><div>訂單日期：${pr.order_date}</div><div>客戶：${esc(pr.customer_code || '')} ${esc(pr.customer_name || '')}</div><div>交貨日期：${pr.delivery_date || ''}</div><div>案場：${esc(pr.site_name)}</div><div>送貨地址：${esc(pr.delivery_address || '')}</div></div>
    <table><tr><th>項次</th><th>櫃號</th><th>項目</th><th>色號</th><th>顏色</th><th class="r">長</th><th>封邊</th><th class="r">寬</th><th>封邊</th><th class="r">板厚</th><th class="r">數量</th><th class="r">才數</th><th>單位</th><th class="r">計價</th><th class="r">金額</th><th>備註</th></tr>
    ${q.lines.map((l) => `<tr><td>${l.part_no}</td><td>${l.cabinet_no} ${esc(l.cabinet_name)}</td><td>${esc(l.name)}</td><td>${esc(l.color_code || '')}</td><td>${esc(l.color_name || '')}</td><td class="r">${num(l.length)}</td><td>${esc(l.edge_l)}</td><td class="r">${num(l.width)}</td><td>${esc(l.edge_w)}</td><td class="r">${num(l.thickness)}</td><td class="r">${l.qty}</td><td class="r">${num(l.cai)}</td><td>${l.unit}</td><td class="r">${num(l.unit_price)}</td><td class="r">${num(l.amount)}</td><td>${esc(l.marks.filter(Boolean).join(' / '))}</td></tr>`).join('')}</table>
    ${q.fees.length ? `<h2>加工費 / 額外費用</h2><table><tr><th>項目</th><th>單位</th><th class="r">數量</th><th class="r">單價</th><th class="r">金額</th><th>備註</th></tr>${q.fees.map((f) => `<tr><td>${esc(f.name)}</td><td>${esc(f.unit || '')}</td><td class="r">${num(f.qty)}</td><td class="r">${num(f.unit_price)}</td><td class="r">${num(f.amount)}</td><td>${esc(f.note || '')}</td></tr>`).join('')}</table>` : ''}
    <table style="width:auto;margin-left:auto"><tr><td>板材牌價小計</td><td class="r">${num(q.subtotal)}</td></tr><tr><td>板材折數 ${+q.discount}</td><td class="r">${num(q.boards_net)}</td></tr><tr><td>加工費</td><td class="r">${num(q.fees_total)}</td></tr><tr><td>安裝</td><td class="r">${num(q.install)}</td></tr><tr><td>運費</td><td class="r">${num(q.freight)}</td></tr><tr><td>稅金 5%</td><td class="r">${num(q.tax)}</td></tr><tr class="tot"><td>總金額</td><td class="r">${num(q.total)}</td></tr></table>`);

  body.querySelector('#printquote').onclick = async () => {
    await saveSettings();
    const qq = await api(`/projects/${p.id}/quote`);
    const m = qq.project.quote_meta || {};
    const valid = m.valid_days || 15;
    printHtml(`報價單 ${pr.order_no}`, `<h1>${esc(settings.company_name || '')}報價單</h1>
      <div class="muted" style="text-align:center">${esc(settings.company_address || '')} ${esc(settings.company_phone || '')} ${settings.company_tax_id ? '統編 ' + esc(settings.company_tax_id) : ''}</div>
      <div class="meta"><div>設計公司：${esc(m.design_company || pr.customer_company || '')}</div><div>報價日期：${today()}</div><div>設計師：${esc(pr.designer || pr.customer_name || '')}</div><div>報價單號：${esc(pr.order_no)}</div>
        <div>屋主/業主名稱：${esc(pr.site_name)}</div><div>聯絡人：${esc(m.contact || '')}</div><div>施工類別：${esc(m.work_type || '')}</div><div>聯絡電話：${esc(m.phone || pr.customer_phone || '')}</div>
        <div>施工地址：${esc(m.site_address || pr.delivery_address || '')}</div><div>預計進場日期：${esc(m.start_date || '')}</div></div>
      <table><tr><th>項次</th><th>項目</th><th>規格</th><th class="r">才數</th><th class="r">數量</th><th class="r">金額</th><th>備註</th></tr>
      ${qq.cabinets.map((c, i) => `<tr><td>${i + 1}</td><td>櫃號 ${c.cabinet_no} ${esc(c.name)}</td><td>${esc(c.spec || '')}</td><td class="r">${num(c.cai)}</td><td class="r">${c.pieces} 片</td><td class="r">${num(c.amount)}</td><td></td></tr>`).join('')}
      ${qq.fees.map((f, i) => `<tr><td>${qq.cabinets.length + i + 1}</td><td>${esc(f.name)}</td><td>${esc(f.unit || '')} × ${num(f.qty)}</td><td></td><td></td><td class="r">${num(f.amount)}</td><td>${esc(f.note || '')}</td></tr>`).join('')}
      <tr><td colspan="5">板材折數 ${+qq.discount}（牌價 ${num(qq.subtotal)}）</td><td class="r">${num(qq.boards_net)}</td><td></td></tr>
      ${+qq.install ? `<tr><td colspan="5">安裝</td><td class="r">${num(qq.install)}</td><td></td></tr>` : ''}${+qq.freight ? `<tr><td colspan="5">運費</td><td class="r">${num(qq.freight)}</td><td></td></tr>` : ''}
      <tr><td colspan="5">小計（未稅）</td><td class="r">${num(qq.taxable)}</td><td></td></tr><tr><td colspan="5">營業稅 5%</td><td class="r">${num(qq.tax)}</td><td></td></tr><tr class="tot"><td colspan="5">總計</td><td class="r">${num(qq.total)}</td><td></td></tr></table>
      <p class="muted">∵本報價單有效期限以報價日期起 ${valid} 日內有效∵</p><p class="pre muted">${esc(settings.quote_terms || '')}</p>
      <div class="meta"><div class="pre"><b>匯款資訊</b><br>${esc(settings.bank_info || '')}</div><div></div></div>
      <div class="sign"><span>裝修戶負責人同意施作簽名：＿＿＿＿＿＿＿＿＿</span><span>聯絡電話：＿＿＿＿＿＿＿＿＿</span><span>日期：＿＿＿＿＿＿</span></div>`);
  };
}

// 設備五金零件單
async function renderPartsList(body, p) {
  const d = await api(`/projects/${p.id}/parts-list`);
  const table = `<table><tr><th style="width:50px">項次</th><th>名稱</th><th class="r" style="width:80px">數量</th><th>規格/型號</th><th>類別</th></tr>
    ${d.items.map((x) => `<tr><td>${x.no}</td><td>${esc(x.name)}</td><td class="r">${num(x.qty)}</td><td>${esc(x.spec || '')}</td><td class="muted">${esc(x.category || '')}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">料單裡沒有五金類板件</td></tr>'}</table>`;
  body.innerHTML = `<div class="card"><div class="row" style="justify-content:space-between"><h3 style="margin:0">設備五金零件單</h3><button class="primary" id="printpl">列印零件單</button></div>
    <div class="row"><span>案名：<b>${esc(p.site_name)}</b></span><span>訂單編號：${esc(p.order_no)}</span><span>製單日期：${d.date}</span><span class="muted small">規格/型號依「基礎資料 → 五金配件」名稱比對帶入，沒對到就留空</span></div>${table}</div>`;
  body.querySelector('#printpl').onclick = () => printHtml(`零件單 ${p.order_no}`, `<h1>設備五金零件單</h1><div class="meta"><div>案名：${esc(p.site_name)}</div><div>製單日期：${d.date}</div><div>訂單編號：${esc(p.order_no)}</div><div>交貨日期：${p.delivery_date || ''}</div></div>${table}`);
}

async function renderLabels(body, p) {
  const rows = await api(`/projects/${p.id}/labels`);
  body.innerHTML = `<div class="card"><h3>標籤列印版 <button id="csv">下載 CSV</button> <span class="muted small">(不含五金列)</span></h3>
    <div class="tablewrap"><table><tr><th>#</th><th>訂單</th><th>案場</th><th>櫃號</th><th>櫃名</th><th>編號</th><th>板材名稱</th><th class="r">長</th><th>封邊</th><th class="r">寬</th><th>封邊</th><th class="r">厚</th><th class="r">數量</th><th>板材廠商</th><th>色號</th><th>封邊色號</th><th>備註</th><th>狀態</th><th>批次</th><th>日期</th></tr>
    ${rows.map((r) => `<tr><td>${r.row}</td><td>${esc(r.order_no)}</td><td>${esc(r.site_name)}</td><td>${r.cabinet_no}</td><td>${esc(r.cabinet_name)}</td><td>${r.part_no}</td><td>${esc(r.name)}</td><td class="r">${num(r.length)}</td><td>${esc(r.edge_l)}</td><td class="r">${num(r.width)}</td><td>${esc(r.edge_w)}</td><td class="r">${num(r.thickness)}</td><td class="r">${r.qty}</td><td>${esc(r.vendor || '')}</td><td>${esc(r.color_code || '')}</td><td>${esc(r.edge_code || '')}</td><td>${esc(r.marks.filter(Boolean).join(' / '))}</td><td>${r.status}</td><td>${r.batch}</td><td>${r.delivery_date || ''}</td></tr>`).join('')}
    </table></div></div>`;
  body.querySelector('#csv').onclick = () => {
    const head = ['訂單', '案場', '櫃號', '櫃名', '專案編號', '板材名稱', '長', '封邊', '寬', '封邊', '厚', '生產數量', '板材廠商', '板材色號', '封邊色號', '備註1', '備註2', '備註3', '備註4', '狀態', '批次', '長封邊首碼', '長封邊A', '寬封邊首碼', '寬封邊尾碼', '日期', '結合器'];
    const lines = rows.map((r) => [r.order_no, r.site_name, r.cabinet_no, r.cabinet_name, r.part_no, r.name, r.length, r.edge_l, r.width, r.edge_w, r.thickness, r.qty, r.vendor, r.color_code, r.edge_code, ...r.marks, r.status, r.batch, r.edge_l_first, r.edge_l_flag, r.edge_w_first, r.edge_w_last, r.delivery_date, r.joint_type].map((v) => `"${String(v ?? '').replace(/"/g, '""')}"`).join(','));
    const blob = new Blob(['﻿' + [head.join(','), ...lines].join('\r\n')], { type: 'text/csv;charset=utf-8' });
    const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `labels_${p.order_no}.csv`; a.click();
  };
}

async function renderSerials(body, p) {
  const rows = await api(`/projects/${p.id}/serials`);
  const done = (k) => rows.filter((r) => r[k]).length;
  const mark = (r, stage) => (r[stage] ? `<button class="link small" data-unscan="${r.serial_no}:${stage}" title="取消此筆掃描">v ✕</button>` : '');
  body.innerHTML = `<div class="card"><h3>流水號 / 掃描確認</h3>
    <div class="row"><label>掃描流水號 <input id="scan" class="num" type="number" placeholder="流水號"></label>
      <button data-stage="cut">開板掃描 (Enter)</button><button data-stage="pack">包裝掃描</button>
      <span class="muted">開板 ${done('cut')}/${rows.length}｜包裝 ${done('pack')}/${rows.length}　流水號固定配給每一片，之後增刪板材不會位移</span></div>
    <div class="tablewrap"><table><tr><th>流水號</th><th>標籤碼</th><th>編號</th><th>櫃號</th><th>板材名稱</th><th>第幾片</th><th>開板確認</th><th>包裝確認</th></tr>
    ${rows.map((r) => `<tr><td>${r.serial_no}</td><td>${esc(r.label)}</td><td>${r.part_no}</td><td>${r.cabinet_no}</td><td>${esc(r.name)}</td><td>${r.piece}</td><td>${mark(r, 'cut')}</td><td>${mark(r, 'pack')}</td></tr>`).join('')}
    </table></div></div>`;
  const scan = async (stage) => {
    const inp = body.querySelector('#scan'); const n = +inp.value; if (!n) return;
    try { const r = await api(`/projects/${p.id}/scans`, { method: 'POST', body: { serial_no: n, stage } }); toast(r.duplicate ? `流水號 ${n} 已掃過` : `流水號 ${n} ${stage === 'cut' ? '開板' : '包裝'}完成`); renderSerials(body, p); }
    catch (err) { toast(err.message, true); inp.select(); }
  };
  body.querySelectorAll('[data-stage]').forEach((b) => (b.onclick = () => scan(b.dataset.stage)));
  body.querySelectorAll('[data-unscan]').forEach((b) => (b.onclick = async () => { const [n, s] = b.dataset.unscan.split(':'); await api(`/projects/${p.id}/scans/${n}/${s}`, { method: 'DELETE' }); renderSerials(body, p); }));
  const scanInp = body.querySelector('#scan');
  scanInp.onkeydown = (e) => { if (e.key === 'Enter') scan('cut'); };
  scanInp.focus();
}

async function renderMaterial(body, p) {
  const m = await api(`/projects/${p.id}/material`);
  body.innerHTML = `<div class="card"><h3>叫料計算 (依色號 × 板厚)</h3>
    <table><tr><th>色號</th><th>色號名稱</th><th class="r">板厚</th><th>封邊色號</th><th class="r">片數</th><th class="r">才數</th><th class="r">封邊條 (m)</th></tr>
    ${m.boards.map((r) => `<tr><td>${esc(r.color_code || '-')}</td><td>${esc(r.color_name || '')}</td><td class="r">${num(r.thickness)}</td><td>${esc(r.edge_code || '')}</td><td class="r">${r.pieces}</td><td class="r">${num(r.cai)}</td><td class="r">${num(r.edge_band_mm / 1000)}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">尚無資料</td></tr>'}
    </table></div>
    <div class="card"><h3>封邊條 (依色號 × 規格) <span class="muted small">規格依板厚分：${m.edge_specs.map((s) => `≤${+s.max_thickness}mm → ${esc(s.spec)}`).join('、')}（基礎資料 → 加工/封邊 可調）</span></h3>
    <table><tr><th>色號</th><th>色號名稱</th><th>封邊色號</th><th>規格</th><th class="r">片數</th><th class="r">長度 (m)</th></tr>
    ${m.edge_bands.map((e) => `<tr><td>${esc(e.color_code || '-')}</td><td>${esc(e.color_name || '')}</td><td>${esc(e.edge_code || '')}</td><td>${esc(e.spec)}</td><td class="r">${e.pieces}</td><td class="r">${num(e.edge_band_mm / 1000)}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">尚無資料</td></tr>'}
    </table></div>
    <div class="card"><h3>五金 / 加工彙總</h3>
    <table><tr><th>類別</th><th>名稱</th><th class="r">數量</th></tr>
    ${m.hardware.map((h) => `<tr><td>${esc(h.category || '')}</td><td>${esc(h.name)}</td><td class="r">${h.qty}</td></tr>`).join('') || '<tr><td colspan="3" class="muted">尚無資料</td></tr>'}
    </table></div>`;
}

// ───────── 客戶 ─────────
async function pageCustomers() {
  const list = await api('/customers');
  const ym = new Date().toISOString().slice(0, 7);
  $app.innerHTML = `<div class="card"><h2>客戶對帳單</h2>
    <form id="stm" class="row"><label>客戶 <select name="cid">${list.map((c) => `<option value="${c.id}">${esc(c.code || '')} ${esc(c.name)}</option>`).join('')}</select></label>
      <label>月份 <input type="month" name="month" value="${ym}"></label><label>依 <select name="by"><option value="delivery">交貨日</option><option value="order">訂貨日</option></select></label>
      <button class="primary">產生對帳單</button></form><div id="stmres"></div></div>
  <div class="card"><h2>新增客戶</h2>
    <form id="newc" class="row">
      <label>客戶編號 <input name="code" placeholder="AA0B001"></label><label>設計師/業務 <input name="name" required></label>
      <label>聯絡電話 <input name="contact_phone"></label><label>公司名稱 <input name="company_name"></label><label>統編 <input name="tax_id"></label>
      <label>公司地址 <input name="address" style="min-width:240px"></label><label>板材折數 <input class="num" name="board_discount" type="number" step="0.01"></label>
      <label>安裝折數 <input class="num" name="install_discount" type="number" step="0.01"></label><button class="primary">建立</button></form></div>
  <div class="card"><h2>客戶列表</h2><p class="muted small">格子直接改即儲存。板材折數（例 0.41）會套進該客戶專案的計價；安裝折數（例 0.2）＝安裝費 ＝ 折後板材金額 × 0.2（在計價頁勾「自動」）。</p>
    <div class="tablewrap"><table class="edit"><tr><th>客戶編號</th><th>設計師/業務</th><th>電話</th><th>公司</th><th>統編</th><th>地址</th><th>公司電話</th><th>板材折數</th><th>安裝折數</th><th></th></tr>
    ${list.map((c) => `<tr data-id="${c.id}"><td><input name="code" value="${esc(c.code || '')}" style="width:90px"></td><td><input name="name" value="${esc(c.name)}" style="width:110px"></td><td><input name="contact_phone" value="${esc(c.contact_phone || '')}" style="width:110px"></td><td><input name="company_name" value="${esc(c.company_name || '')}" style="width:150px"></td><td><input name="tax_id" value="${esc(c.tax_id || '')}" style="width:90px"></td><td><input name="address" value="${esc(c.address || '')}" style="width:220px"></td><td><input name="company_phone" value="${esc(c.company_phone || '')}" style="width:110px"></td><td><input name="board_discount" type="number" step="0.001" class="num" value="${c.board_discount ?? ''}"></td><td><input name="install_discount" type="number" step="0.001" class="num" value="${c.install_discount ?? ''}"></td><td><button class="link danger" data-cdel="${c.id}">✕</button></td></tr>`).join('') || '<tr><td colspan="10" class="muted">尚無客戶</td></tr>'}
  </table></div></div>`;
  $app.querySelectorAll('tr[data-id]').forEach((tr) => tr.querySelectorAll('input').forEach((i) => { i.onchange = async () => { const d = rowData(tr); if (!d.name) return toast('名稱不可空白', true); try { await api('/customers/' + tr.dataset.id, { method: 'PUT', body: d }); state.customers = null; toast('已儲存'); } catch (err) { toast(err.message, true); } }; i.onkeydown = (e) => { if (e.key === 'Enter') i.blur(); }; }));
  $app.querySelectorAll('[data-cdel]').forEach((b) => (b.onclick = async () => { if (!confirm('刪除此客戶？（仍有專案的客戶無法刪除）')) return; try { await api('/customers/' + b.dataset.cdel, { method: 'DELETE' }); state.customers = null; pageCustomers(); } catch (err) { toast(err.message, true); } }));
  $app.querySelector('#newc').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    for (const k of ['board_discount', 'install_discount']) f[k] = n0(f[k]);
    for (const k in f) if (f[k] === '') f[k] = null;
    await api('/customers', { method: 'POST', body: f }); state.customers = null; toast('已建立'); pageCustomers();
  };
  $app.querySelector('#stm').onsubmit = async (e) => {
    e.preventDefault();
    const f = Object.fromEntries(new FormData(e.target));
    if (!f.cid) return toast('請先建立客戶', true);
    const s = await api(`/customers/${f.cid}/statement?month=${f.month}&by=${f.by}`);
    const settings = await api('/settings');
    const cu = s.customer;
    const html = `<h1>客戶對帳單</h1><div class="muted" style="text-align:center">${esc(settings.company_name || '')}</div>
      <div class="meta"><div>對帳月份：${s.month}（依${s.by === 'delivery' ? '交貨日' : '訂貨日'}）</div><div>客戶代號：${esc(cu.code || '')}</div><div>客戶名稱：${esc(cu.company_name || cu.name)}</div><div>統一編號：${esc(cu.tax_id || '')}</div><div>客戶地址：${esc(cu.address || '')}</div><div>電話：${esc(cu.contact_phone || cu.company_phone || '')}</div></div>
      <table><tr><th>出貨日期</th><th>出貨單編號</th><th>案場</th><th class="r">片數</th><th class="r">才數</th><th class="r">未稅</th><th class="r">稅</th><th class="r">小計</th></tr>
      ${s.lines.map((l) => `<tr><td>${fmtDate(l.date)}</td><td>${esc(l.order_no)}</td><td>${esc(l.site_name)}</td><td class="r">${l.pieces}</td><td class="r">${num(l.cai)}</td><td class="r">${num(l.net)}</td><td class="r">${num(l.tax)}</td><td class="r">${num(l.total)}</td></tr>`).join('') || '<tr><td colspan="8">本月無訂單</td></tr>'}
      <tr class="tot"><td colspan="5">本期合計</td><td class="r">${num(s.total_net)}</td><td class="r">${num(s.total_tax)}</td><td class="r">${num(s.total)}</td></tr></table>
      <div class="meta"><div>本期折讓：＿＿＿＿＿</div><div>前期應收：＿＿＿＿＿</div><div>本期已收：＿＿＿＿＿</div><div>預收款：＿＿＿＿＿</div><div><b>本期應收：${num(s.total)}</b></div><div>總應收款：＿＿＿＿＿</div></div>
      <p class="pre muted">${esc(settings.statement_note || '')}</p>`;
    $app.querySelector('#stmres').innerHTML = `<div class="row" style="justify-content:space-between;margin-top:8px"><span>${s.lines.length} 張訂單，本期總計 <b>${num(s.total)}</b></span><button id="stmprint">列印對帳單</button></div><div class="printprev">${html}</div>`;
    $app.querySelector('#stmprint').onclick = () => printHtml(`對帳單 ${cu.code || cu.name} ${s.month}`, html);
  };
  window.maybeAutoTour('customers');
}

// ───────── 基礎資料 ─────────
async function pageMaster(tab = 'colors') {
  const tabs = [['colors', '色號 / 單價'], ['catalog', '零件目錄'], ['process', '加工/封邊'], ['marks', '標記'], ['hardware', '五金配件'], ['vendors', '廠商'], ['lookups', '下拉清單'], ['cabprices', '牌價表'], ['cost', '成本分析'], ['company', '公司資料']];
  $app.innerHTML = `<div class="tabs">${tabs.map(([k, v]) => `<button class="${tab == k ? 'active' : ''}" onclick="location.hash='#/master/${k}'">${v}</button>`).join('')}</div><div id="mbody" class="card">載入中…</div>`;
  const b = document.getElementById('mbody');
  if (tab === 'colors') await masterColors(b);
  else if (tab === 'catalog') await masterCatalog(b);
  else if (tab === 'process') await masterProcess(b);
  else if (tab === 'marks') await masterSimple(b, { path: '/master/marks', idKey: 'id', title: '標記（備註欄常用代碼）', cols: [['name', '標記', 'text', 120], ['code', '代碼', 'text', 70], ['number', '編號', 'number', 70]], required: 'name' });
  else if (tab === 'hardware') await masterHardware(b);
  else if (tab === 'vendors') await masterSimple(b, { path: '/master/vendors', idKey: 'id', title: '廠商', cols: [['name', '廠商', 'text', 100], ['company_name', '公司名稱', 'text', 180], ['tax_id', '統編', 'text', 90], ['address', '登記地址', 'text', 220], ['factory_address', '工廠地址', 'text', 220], ['phone', '電話', 'text', 120]], required: 'name' });
  else if (tab === 'cabprices') await masterCabinetPrices(b);
  else if (tab === 'cost') await masterCost(b);
  else if (tab === 'company') await masterCompany(b);
  else await masterLookups(b);
  window.maybeAutoTour('master');
}

// 加工牌價 (門板加工 / 五金配件牌價 / 特殊加工板材) + 封邊條規格
async function masterProcess(b) {
  const kinds = ['門板加工', '五金配件牌價', '特殊加工板材'];
  const cfgTable = { path: '/master/process-prices', idKey: 'id', title: '加工 / 五金牌價', search: false,
    cols: [['kind', '類型', 'select', 110, kinds], ['name', '項目', 'text', 220], ['spec', '規格', 'text', 110], ['unit', '單位', 'text', 60], ['price', '牌價', 'number', 80], ['note', '備註', 'text', 160]], required: 'name' };
  b.innerHTML = `<div id="pp"></div><hr style="border:none;border-top:1px solid var(--line);margin:14px 0"><div id="es"></div>`;
  await masterSimple(b.querySelector('#pp'), cfgTable);
  const es = b.querySelector('#es');
  const renderEs = async () => {
    const specs = await api('/master/edge-specs');
    es.innerHTML = `<h3>封邊條規格（依板厚分組，叫料計算用）</h3><p class="muted small">板厚 ≤ 「上限」的板材歸到該規格，由小到大比對。例：≤6 → 2分、≤19 → 22*1、≤26 → 29*1、其餘 → 麻雙。</p>
      <table class="edit" style="width:auto"><tr><th>板厚上限 (mm)</th><th>規格名稱</th><th></th></tr>
      <tr class="newrow"><td><input name="max_thickness" type="number" step="0.1" class="num"></td><td><input name="spec" placeholder="例：封邊條22*1"></td><td><button class="primary small" id="esadd">新增</button></td></tr>
      ${specs.map((s) => `<tr data-id="${s.id}"><td><input name="max_thickness" type="number" step="0.1" class="num" value="${+s.max_thickness}"></td><td><input name="spec" value="${esc(s.spec)}"></td><td><button class="link danger" data-del="${s.id}">✕</button></td></tr>`).join('')}</table>`;
    es.querySelector('#esadd').onclick = async () => { const d = rowData(es.querySelector('tr.newrow')); if (d.max_thickness == null || !d.spec) return toast('請填上限與規格', true); await api('/master/edge-specs', { method: 'POST', body: d }); renderEs(); };
    es.querySelectorAll('tr[data-id]').forEach((tr) => tr.querySelectorAll('input').forEach((i) => { i.onchange = async () => { await api('/master/edge-specs/' + tr.dataset.id, { method: 'PUT', body: rowData(tr) }); toast('已儲存'); renderEs(); }; }));
    es.querySelectorAll('[data-del]').forEach((x) => (x.onclick = async () => { await api('/master/edge-specs/' + x.dataset.del, { method: 'DELETE' }); renderEs(); }));
  };
  await renderEs();
}

// 五金配件：可編輯表格 + 庫存 + 進銷貨紀錄
async function masterHardware(b) {
  const cfg = { path: '/master/hardware', idKey: 'id', title: '五金配件', search: true,
    cols: [['vendor', '廠商', 'text', 90], ['product_name', '產品名稱', 'text', 180], ['model', '型號', 'text', 110], ['spec', '規格', 'text', 140], ['purchase_unit', '進貨單位', 'text', 90], ['sales_unit', '銷貨單位', 'text', 70], ['list_price', '牌價', 'number', 80], ['note', '備註', 'text', 140]], required: 'product_name',
    extraHead: '<th class="r">庫存</th><th>紀錄</th>',
    extraCells: async () => { const st = await api('/master/hardware-stock'); return (r) => `<td class="r auto">${num(st[r.id] ?? 0)}</td><td><button class="link small" data-txn="${r.id}">進銷貨</button></td>`; } };
  await masterSimple(b, cfg);
  b.querySelectorAll('[data-txn]').forEach((btn) => (btn.onclick = () => openTxns(+btn.dataset.txn, b)));
}
async function openTxns(hid, b) {
  const KIND = { in: '進貨', out: '銷貨', return_in: '進貨退回', return_out: '銷貨退回' };
  const v = document.getElementById('viewer') || (() => { const d = document.createElement('div'); d.id = 'viewer'; d.className = 'modal'; document.body.appendChild(d); return d; })();
  const draw = async () => {
    const [d, hw] = await Promise.all([api(`/master/hardware/${hid}/txns`), api('/master/hardware')]);
    const h = hw.find((x) => x.id === hid);
    v.style.display = 'flex';
    v.innerHTML = `<div class="modal-box" style="width:min(96vw,900px)">
      <div class="row" style="justify-content:space-between"><b>${esc(h.product_name)} ${esc(h.model || '')}　進銷貨紀錄　庫存 <span class="pill">${num(d.stock)}</span></b><button id="vclose">關閉</button></div>
      <form id="txnf" class="row"><label>類型 <select name="kind">${Object.entries(KIND).map(([k, t]) => `<option value="${k}">${t}</option>`).join('')}</select></label><label>日期 <input type="date" name="txn_date" value="${today()}"></label>
        <label>數量 <input class="num" name="qty" type="number" step="0.01" required></label><label>金額 <input class="num" name="amount" type="number" step="0.01"></label><label>傳票編號 <input name="voucher_no" class="num"></label><label>案場 <input name="site"></label><label>備註 <input name="note"></label><button class="primary">新增</button></form>
      <div class="tablewrap"><table><tr><th>日期</th><th>類型</th><th class="r">數量</th><th class="r">金額</th><th>傳票</th><th>案場</th><th>備註</th><th></th></tr>
      ${d.txns.map((t) => `<tr><td>${fmtDate(t.txn_date)}</td><td>${KIND[t.kind]}</td><td class="r">${num(t.qty)}</td><td class="r">${num(t.amount)}</td><td>${esc(t.voucher_no || '')}</td><td>${esc(t.site || '')}</td><td>${esc(t.note || '')}</td><td><button class="link danger" data-tdel="${t.id}">✕</button></td></tr>`).join('') || '<tr><td colspan="8" class="muted">尚無紀錄</td></tr>'}</table></div></div>`;
    v.querySelector('#vclose').onclick = () => { v.style.display = 'none'; masterHardware(b); };
    v.onclick = (e) => { if (e.target === v) { v.style.display = 'none'; masterHardware(b); } };
    v.querySelector('#txnf').onsubmit = async (e) => { e.preventDefault(); const f = Object.fromEntries(new FormData(e.target)); f.qty = +f.qty; f.amount = n0(f.amount); for (const k in f) if (f[k] === '') f[k] = null; try { await api(`/master/hardware/${hid}/txns`, { method: 'POST', body: f }); draw(); } catch (err) { toast(err.message, true); } };
    v.querySelectorAll('[data-tdel]').forEach((x) => (x.onclick = async () => { await api('/master/hardware-txns/' + x.dataset.tdel, { method: 'DELETE' }); draw(); }));
  };
  await draw();
}

// 牌價表：可改底價/係數/折數，右邊自動算 (對外版可列印)
async function masterCabinetPrices(b) {
  const rows = await api('/master/cabinet-prices');
  const inp = (r, k, w = 70, step = '0.01') => `<input name="${k}" type="number" step="${step}" class="num" style="width:${w}px;min-width:${w}px" value="${r[k] ?? ''}">`;
  const txt = (r, k, w = 120) => `<input name="${k}" value="${esc(r[k] ?? '')}" style="width:${w}px;min-width:${w}px">`;
  const row = (r, isNew) => `<tr ${isNew ? 'class="newrow"' : `data-id="${r.id}"`}><td>${inp(r, 'seq', 50, '1')}</td><td>${txt(r, 'name', 150)}</td><td>${txt(r, 'spec', 90)}</td><td>${inp(r, 'factor', 60, '0.001')}</td><td>${inp(r, 'base_price')}</td><td>${inp(r, 'sell_price')}</td>
    <td>${inp(r, 'designer_discount', 60, '0.001')}</td><td>${inp(r, 'employee_discount_draw', 60, '0.001')}</td><td>${inp(r, 'employee_discount', 60, '0.001')}</td><td>${inp(r, 'install_per_cm', 60)}</td>
    ${isNew ? '<td colspan="6"></td>' : `<td class="auto r">${num(r.sell_calc)}</td><td class="auto r">${num(r.designer_price)}</td><td class="auto r">${num(r.designer_price_install)}</td><td class="auto r">${num(r.employee_price_draw)}</td><td class="auto r">${num(r.employee_price_draw_install)}</td><td class="auto r">${num(r.employee_price)}</td>`}
    <td>${isNew ? '<button class="primary small" id="cpadd">新增</button>' : `<button class="link danger" data-del="${r.id}">✕</button>`}</td></tr>`;
  b.innerHTML = `<div class="row" style="justify-content:space-between"><h3 style="margin:0">櫃體牌價表（對公司內部）</h3><button id="cpprint">列印對外賣價表</button></div>
    <p class="muted small">白格可改：係數（1.05＝含稅）、底價、賣價（留空＝底價×係數）、折數。藍格自動算：賣價、業務&設計師實價（賣價×折數）、含安裝（×1.2）、員工自用實價。</p>
    <div class="tablewrap"><table class="edit"><tr><th>#</th><th>品名</th><th>規格 高x深</th><th>係數</th><th>底價</th><th>賣價(手填)</th><th>業務折數</th><th>員工折數(含製圖)</th><th>員工折數</th><th>安裝/公分</th><th class="r">賣價</th><th class="r">業務實價</th><th class="r">業務含安裝</th><th class="r">員工(含製圖)</th><th class="r">員工含安裝</th><th class="r">員工實價</th><th></th></tr>
    ${row({ factor: 1.05, designer_discount: 0.6, employee_discount_draw: 0.5, employee_discount: 0.47 }, true)}${rows.map((r) => row(r, false)).join('')}</table></div>`;
  const save = async (tr, method, path) => { const d = rowData(tr); if (!d.name) return toast('請填品名', true); try { await api(path, { method, body: d }); masterCabinetPrices(b); } catch (err) { toast(err.message, true); } };
  b.querySelector('#cpadd').onclick = () => save(b.querySelector('tr.newrow'), 'POST', '/master/cabinet-prices');
  b.querySelectorAll('tr[data-id]').forEach((tr) => tr.querySelectorAll('input').forEach((i) => { i.onchange = () => save(tr, 'PUT', '/master/cabinet-prices/' + tr.dataset.id); i.onkeydown = (e) => { if (e.key === 'Enter') i.blur(); }; }));
  b.querySelectorAll('[data-del]').forEach((x) => (x.onclick = async () => { if (!confirm('刪除此列？')) return; await api('/master/cabinet-prices/' + x.dataset.del, { method: 'DELETE' }); masterCabinetPrices(b); }));
  b.querySelector('#cpprint').onclick = async () => { const s = await api('/settings'); printHtml('對外賣價表', `<h1>${esc(s.company_name || '')} 價目表</h1><div class="muted" style="text-align:center">${today()}</div>
    <table><tr><th>品名</th><th>規格 高x深</th><th class="r">賣價</th><th class="r">業務&設計師板材實價/尺(不含安裝)</th><th class="r">業務&設計師實價/尺(含安裝)</th></tr>
    ${rows.map((r) => `<tr><td>${esc(r.name)}</td><td>${esc(r.spec || '')}</td><td class="r">${num(r.base_price)}</td><td class="r">${num(r.designer_price)}</td><td class="r">${num(r.designer_price_install)}</td></tr>`).join('')}</table>`); };
}

// 板材成本分析：改進貨成本 / 材數 / 封邊 / 毛利，右邊自動算每材成本與實價
async function masterCost(b) {
  const rows = await api('/master/cost-analysis');
  const inp = (r, k, w = 70, step = '0.01') => `<input name="${k}" type="number" step="${step}" class="num" style="width:${w}px;min-width:${w}px" value="${r[k] ?? ''}">`;
  const txt = (r, k, w = 80) => `<input name="${k}" value="${esc(r[k] ?? '')}" style="width:${w}px;min-width:${w}px">`;
  const row = (r, isNew) => `<tr ${isNew ? 'class="newrow"' : `data-id="${r.id}"`}><td>${txt(r, 'vendor', 60)}</td><td>${txt(r, 'series', 70)}</td><td>${txt(r, 'color_code', 60)}</td><td>${txt(r, 'spec', 80)}</td><td>${txt(r, 'base_material', 90)}</td><td>${txt(r, 'face', 60)}</td>
    <td>${inp(r, 'list_cost')}</td><td>${inp(r, 'net_cost')}</td><td>${inp(r, 'full_cai', 50)}</td><td>${inp(r, 'usable_cai', 50)}</td><td>${inp(r, 'edge_m_per_cai', 50, '0.001')}</td><td>${inp(r, 'edge_cost', 50)}</td><td>${inp(r, 'margin', 60)}</td>
    ${isNew ? '<td colspan="8"></td>' : `<td class="auto r">${num(r.taxed_cost)}</td><td class="auto r">${num(r.per_cai)}</td><td class="auto r">${num(r.per_cai_loss)}</td><td class="auto r">${num(r.edge_total)}</td><td class="auto r">${num(r.make_cost)}</td><td class="auto r">${num(r.price_net)}</td><td class="auto r">${r.margin_rate == null ? '' : num(r.margin_rate) + '%'}</td><td class="auto r">${num(r.price_taxed)}</td>`}
    <td>${isNew ? '<button class="primary small" id="csadd">新增</button>' : `<button class="link danger" data-del="${r.id}">✕</button>`}</td></tr>`;
  b.innerHTML = `<h3>板材成本分析</h3>
    <p class="muted small">白格可改：進貨牌價、未稅成本（留空＝牌價）、滿板材數、可用材數、每材封邊公尺、封邊成本/元、毛利。藍格自動：完稅成本（×1.05）、每材單價、含損料每材單價、封邊製成成本、製成成本、實價(未稅)、毛利率、實價(完稅)。</p>
    <div class="tablewrap"><table class="edit"><tr><th>廠商</th><th>系列</th><th>色號</th><th>規格</th><th>基材</th><th>面材</th><th>進貨牌價</th><th>未稅成本</th><th>滿板材</th><th>可用材</th><th>封邊m/材</th><th>封邊$/m</th><th>毛利</th><th class="r">完稅成本</th><th class="r">每材</th><th class="r">含損料</th><th class="r">封邊</th><th class="r">製成成本</th><th class="r">實價未稅</th><th class="r">毛利率</th><th class="r">實價完稅</th><th></th></tr>
    ${row({ full_cai: 32, usable_cai: 26, edge_m_per_cai: 1.2 }, true)}${rows.map((r) => row(r, false)).join('')}</table></div>`;
  const save = async (tr, method, path) => { try { await api(path, { method, body: rowData(tr) }); masterCost(b); } catch (err) { toast(err.message, true); } };
  b.querySelector('#csadd').onclick = () => save(b.querySelector('tr.newrow'), 'POST', '/master/cost-analysis');
  b.querySelectorAll('tr[data-id]').forEach((tr) => tr.querySelectorAll('input').forEach((i) => { i.onchange = () => save(tr, 'PUT', '/master/cost-analysis/' + tr.dataset.id); i.onkeydown = (e) => { if (e.key === 'Enter') i.blur(); }; }));
  b.querySelectorAll('[data-del]').forEach((x) => (x.onclick = async () => { if (!confirm('刪除此列？')) return; await api('/master/cost-analysis/' + x.dataset.del, { method: 'DELETE' }); masterCost(b); }));
}

// 公司資料：報價單 / 對帳單 / 價目表表頭
async function masterCompany(b) {
  const s = await api('/settings');
  const fields = [['company_name', '公司名稱', 'input'], ['company_tax_id', '統一編號', 'input'], ['company_phone', '電話', 'input'], ['company_address', '地址', 'input'], ['bank_info', '匯款資訊（報價單右上）', 'textarea'], ['quote_terms', '報價單條款（報價單下方）', 'textarea'], ['statement_note', '對帳單備註', 'textarea']];
  b.innerHTML = `<h3>公司資料</h3><p class="muted small">用在報價單、對帳單、對外賣價表的表頭與備註。</p><form id="cf" style="display:grid;gap:8px;max-width:720px">
    ${fields.map(([k, label, t]) => `<label style="display:flex;flex-direction:column;font-size:12px;color:var(--muted)">${label}${t === 'textarea' ? `<textarea name="${k}" rows="${Math.max(4, (s[k] || '').split('\n').length + 1)}" style="line-height:1.6">${esc(s[k] || '')}</textarea>` : `<input name="${k}" value="${esc(s[k] || '')}">`}</label>`).join('')}
    <p class="muted small" style="margin:0">多行欄位每一行就是列印時的一行（Enter 換行）；條款建議一個 ● 一行。</p>
    <div><button class="primary">儲存</button></div></form>`;
  b.querySelector('#cf').onsubmit = async (e) => { e.preventDefault(); await api('/settings', { method: 'PUT', body: Object.fromEntries(new FormData(e.target)) }); toast('已儲存'); };
}

// 下拉清單：左邊清單種類，右邊值的表格 (新增 / 改名 / 上下移 / 刪除)；狀態代碼只能看
const LOOKUP_INFO = {
  '板厚': '專案板厚下拉選項（mm）。新專案與表頭都從這裡選。',
  '設計師': '專案「業務/設計師」的建議清單。',
  '基材': '板材基材（木芯板、發泡板…），供查詢參考。',
  '板材廠商': '板材廠商選項，供查詢參考。',
  '計價單位': '計價單位（才、片、支、組、米）。',
  '狀態': '板材狀態代碼（A 新增、B 補料…），會印在標籤上。代碼被板材引用，這裡只能查看。',
};
let lkSel = '板厚';
async function masterLookups(b) {
  const l = await api('/master/lookups');
  state.lookups = l;
  const fixed = ['板厚', '設計師', '基材', '板材廠商', '計價單位'];
  const kinds = [...fixed, ...Object.keys(l).filter((k) => !fixed.includes(k) && k !== '狀態'), '狀態'].filter((k) => l[k]);
  if (!l[lkSel]) lkSel = kinds[0];
  const ro = lkSel === '狀態';
  const vals = l[lkSel] || [];
  const reload = async () => { await masterLookups(b); };
  b.innerHTML = `
  <div class="split" style="grid-template-columns:220px 1fr">
    <aside>
      <div class="muted small" style="margin-bottom:6px">清單</div>
      <ul class="catlist">${kinds.map((k) => `<li class="${k === lkSel ? 'active' : ''}" data-kind="${esc(k)}">${esc(k)} <span class="muted">${(l[k] || []).length}</span></li>`).join('')}</ul>
    </aside>
    <div>
      <h3 style="margin:0 0 4px">${esc(lkSel)} <span class="muted small">(${vals.length})</span></h3>
      <p class="muted small">${esc(LOOKUP_INFO[lkSel] || '')}</p>
      ${ro ? '' : `<div class="row" style="margin:8px 0"><input id="lknew" placeholder="${lkSel === '板厚' ? '例：17.2' : '新值'}" style="min-width:200px"> <button class="primary" id="lkadd">加入「${esc(lkSel)}」</button></div>`}
      <div class="tablewrap"><table class="edit">
        <tr><th style="width:40px">#</th><th>${ro ? '代碼' : '值（可直接改）'}</th>${ro ? '<th>名稱</th>' : ''}<th style="width:150px"></th></tr>
        ${vals.map((x, i) => ro
          ? `<tr><td class="muted">${i + 1}</td><td><b>${esc(x.code)}</b></td><td>${esc(x.name)}</td><td></td></tr>`
          : `<tr data-val="${esc(x)}"><td class="muted">${i + 1}</td><td><input name="value" value="${esc(x)}" style="min-width:200px"></td>
             <td class="nowrap"><button class="link" data-move="up" title="上移">↑</button><button class="link" data-move="down" title="下移">↓</button><button class="link danger" data-del="1">✕ 移除</button></td></tr>`).join('') || '<tr><td colspan="4" class="muted">尚無項目</td></tr>'}
      </table></div>
    </div>
  </div>`;
  b.querySelectorAll('[data-kind]').forEach((li) => (li.onclick = () => { lkSel = li.dataset.kind; reload(); }));
  if (ro) return;
  const add = async () => {
    const v = b.querySelector('#lknew').value.trim(); if (!v) return;
    try { await api('/master/lookups', { method: 'POST', body: { kind: lkSel, value: v } }); toast('已新增'); reload(); } catch (err) { toast(err.message, true); }
  };
  b.querySelector('#lkadd').onclick = add;
  b.querySelector('#lknew').onkeydown = (e) => { if (e.key === 'Enter') add(); };
  b.querySelectorAll('tr[data-val]').forEach((tr) => {
    const v = tr.dataset.val;
    const u = `/master/lookups/${encodeURIComponent(lkSel)}/${encodeURIComponent(v)}`;
    const inp = tr.querySelector('input[name=value]');
    inp.onchange = async () => { try { await api(u, { method: 'PUT', body: { value: inp.value } }); toast('已更新'); reload(); } catch (err) { toast(err.message, true); inp.value = v; } };
    inp.onkeydown = (e) => { if (e.key === 'Enter') inp.blur(); };
    tr.querySelectorAll('[data-move]').forEach((m) => (m.onclick = async () => { await api('/master/lookups/move', { method: 'POST', body: { kind: lkSel, value: v, direction: m.dataset.move } }); reload(); }));
    tr.querySelector('[data-del]').onclick = async () => { if (!confirm(`從「${lkSel}」移除「${v}」？`)) return; await api(u, { method: 'DELETE' }); reload(); };
  });
}

// 把 tr[data-id] 內的 input 值收成物件
function rowData(tr) {
  const d = {};
  tr.querySelectorAll('input,select').forEach((i) => { d[i.name] = i.type === 'number' ? n0(i.value) : (i.value.trim() || null); });
  return d;
}

// 通用可編輯表格：標記 / 五金 / 廠商。每列改完即存；最上面一列是新增。
async function masterSimple(b, cfg) {
  const render = async () => {
    const q = b.querySelector('#msq')?.value || '';
    const rows = await api(cfg.path + (cfg.search && q ? '?q=' + encodeURIComponent(q) : ''));
    const extra = cfg.extraCells ? await cfg.extraCells() : () => '';
    const inp = (c, v, extraAttr = '') => c[2] === 'select'
      ? `<select name="${c[0]}">${opt(c[4], v, false)}</select>`
      : `<input name="${c[0]}" type="${c[2]}" ${c[2] === 'number' ? 'step="0.01"' : ''} value="${esc(v ?? '')}" style="width:${c[3]}px;min-width:${c[3]}px" ${extraAttr}>`;
    b.innerHTML = `<div class="row" style="justify-content:space-between"><h3 style="margin:0">${esc(cfg.title)} <span class="muted small">(${rows.length})</span></h3>
        ${cfg.search ? `<label>搜尋 <input id="msq" value="${esc(q)}"></label>` : ''}</div>
      <p class="muted small">直接在格子裡改，按 Enter 或點別處即儲存；最上面一列填好按「新增」。</p>
      <div class="tablewrap"><table class="edit">
        <tr>${cfg.cols.map((c) => `<th>${c[1]}</th>`).join('')}${cfg.extraHead || ''}<th></th></tr>
        <tr class="newrow">${cfg.cols.map((c) => `<td>${inp(c, '', c[0] === cfg.required ? 'required placeholder="必填"' : '')}</td>`).join('')}${cfg.extraHead ? '<td></td><td></td>' : ''}<td><button class="primary small" id="msadd">新增</button></td></tr>
        ${rows.map((r) => `<tr data-id="${r[cfg.idKey]}">${cfg.cols.map((c) => `<td>${inp(c, r[c[0]])}</td>`).join('')}${extra(r)}<td><button class="link danger" data-del="${r[cfg.idKey]}">✕</button></td></tr>`).join('')}
      </table></div>`;
    if (cfg.search) { const s = b.querySelector('#msq'); s.onkeydown = (e) => e.key === 'Enter' && render(); }
    b.querySelector('#msadd').onclick = async () => {
      const d = rowData(b.querySelector('tr.newrow'));
      if (!d[cfg.required]) return toast(`請填 ${cfg.cols.find((c) => c[0] === cfg.required)[1]}`, true);
      try { await api(cfg.path, { method: 'POST', body: d }); toast('已新增'); render(); } catch (err) { toast(err.message, true); }
    };
    b.querySelectorAll('tr[data-id]').forEach((tr) => {
      tr.querySelectorAll('input,select').forEach((i) => {
        i.onchange = async () => { try { await api(`${cfg.path}/${tr.dataset.id}`, { method: 'PUT', body: rowData(tr) }); toast('已儲存'); } catch (err) { toast(err.message, true); } };
        i.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); i.blur(); } };
      });
    });
    b.querySelectorAll('[data-del]').forEach((x) => (x.onclick = async () => { if (!confirm('確定刪除這一列？')) return; await api(`${cfg.path}/${x.dataset.del}`, { method: 'DELETE' }); render(); }));
  };
  await render();
}

// 色號 / 單價：色號 × 板厚 矩陣，可直接改單價，CSV 匯出入
async function masterColors(b) {
  const [ths, vendorsList] = await Promise.all([api('/master/thicknesses'), api('/master/vendors-list')]);
  const render = async () => {
    const q = b.querySelector('#cq')?.value || '', vendor = b.querySelector('#cv')?.value || '';
    const rows = await api(`/master/colors?with_prices=true&limit=400&q=${encodeURIComponent(q)}&vendor=${encodeURIComponent(vendor)}`);
    const th = (t) => `${t}`;
    b.innerHTML = `<div class="row" style="justify-content:space-between">
        <h3 style="margin:0">色號 / 單價 <span class="muted small">(顯示 ${rows.length} 筆${rows.length >= 400 ? '，請用搜尋縮小' : ''})</span></h3>
        <span class="row"><label>搜尋色號 / 板名 / 封邊 <input id="cq" value="${esc(q)}"></label><label>廠商 <select id="cv">${opt(vendorsList, vendor)}</select></label>
          <button id="csvdl">下載 CSV</button><label class="chk"><input type="file" id="csvup" accept=".csv" style="display:none"><button type="button" id="csvbtn">匯入 CSV</button></label></span></div>
      <p class="muted small">單價＝每才（元），欄標題是板厚 (mm)。直接改格子即儲存，清空＝刪除該單價。CSV 匯入：同「下載 CSV」格式，空白＝不變，「-」＝刪除。</p>
      <div class="tablewrap"><table class="edit">
        <tr><th>色號</th><th>板名</th><th>廠商</th><th>封邊色號</th><th>系列</th>${ths.map((t) => `<th class="r">${th(t)}</th>`).join('')}<th></th></tr>
        <tr class="newrow"><td><input name="code" required placeholder="新色號" style="width:80px;min-width:80px"></td><td><input name="board_name" style="width:110px"></td><td><input name="vendor" list="vendorlist" style="width:80px"></td><td><input name="edge_code" style="width:90px"></td><td><input name="series" style="width:60px"></td>
          ${ths.map((t) => `<td><input name="p_${t}" type="number" step="0.01" class="num" style="width:64px;min-width:64px"></td>`).join('')}<td><button class="primary small" id="cadd">新增</button></td></tr>
        ${rows.map((r) => `<tr data-id="${esc(r.code)}"><td><b>${esc(r.code)}</b><input type="hidden" name="code" value="${esc(r.code)}"></td>
          <td><input name="board_name" value="${esc(r.board_name || '')}" style="width:110px"></td><td><input name="vendor" list="vendorlist" value="${esc(r.vendor || '')}" style="width:80px"></td>
          <td><input name="edge_code" value="${esc(r.edge_code || '')}" style="width:90px"></td><td><input name="series" value="${esc(r.series || '')}" style="width:60px"></td>
          ${ths.map((t) => `<td><input name="p_${t}" type="number" step="0.01" class="num" style="width:64px;min-width:64px" value="${r.prices?.[String(t)] ?? ''}"></td>`).join('')}
          <td><button class="link danger" data-del="${esc(r.code)}">✕</button></td></tr>`).join('')}
      </table></div><datalist id="vendorlist">${vendorsList.map((v) => `<option value="${esc(v)}">`).join('')}</datalist>`;
    const body = (tr) => {
      const d = rowData(tr); const prices = {};
      ths.forEach((t) => { const v = d[`p_${t}`]; prices[String(t)] = v === null || v === undefined ? null : v; delete d[`p_${t}`]; });
      return { ...d, prices };
    };
    b.querySelector('#cq').onkeydown = (e) => e.key === 'Enter' && render();
    b.querySelector('#cv').onchange = render;
    b.querySelector('#csvdl').onclick = () => { window.location = '/api/master/colors-export.csv'; };
    b.querySelector('#csvbtn').onclick = () => b.querySelector('#csvup').click();
    b.querySelector('#csvup').onchange = async (e) => {
      const f = e.target.files[0]; if (!f) return;
      const fd = new FormData(); fd.append('file', f);
      try { const r = await api('/master/colors-import-csv', { method: 'POST', body: fd }); toast(`匯入 ${r.rows} 個色號、${r.prices} 筆單價${r.errors.length ? `，${r.errors.length} 個錯誤` : ''}`); if (r.errors.length) alert(r.errors.join('\n')); state.colors = null; render(); }
      catch (err) { toast(err.message, true); }
    };
    b.querySelector('#cadd').onclick = async () => {
      const d = body(b.querySelector('tr.newrow'));
      if (!d.code) return toast('請填色號', true);
      try { await api('/master/colors', { method: 'POST', body: d }); toast('已新增'); state.colors = null; render(); } catch (err) { toast(err.message, true); }
    };
    b.querySelectorAll('tr[data-id]').forEach((tr) => {
      tr.querySelectorAll('input').forEach((i) => {
        i.onchange = async () => { try { await api('/master/colors/' + encodeURIComponent(tr.dataset.id), { method: 'PUT', body: body(tr) }); toast('已儲存'); state.colors = null; } catch (err) { toast(err.message, true); } };
        i.onkeydown = (e) => { if (e.key === 'Enter') { e.preventDefault(); i.blur(); } };
      });
    });
    b.querySelectorAll('[data-del]').forEach((x) => (x.onclick = async () => { if (!confirm(`刪除色號 ${x.dataset.del}？（仍被板材使用時會拒絕）`)) return; try { await api('/master/colors/' + encodeURIComponent(x.dataset.del), { method: 'DELETE' }); state.colors = null; render(); } catch (err) { toast(err.message, true); } }));
  };
  await render();
}

// 零件目錄：左側類別 (依拆單順序)，右側該類別項目表格：搜尋、改名、上下移、搬類別、刪除、新增
const CATEGORY_ORDER = ['桶身', '內部', '外部', '抽屜', '抽箱', '抽盤_不見軌道', '床架_臥塌', '內部五金', '外部五金', '抽屜五金', '衣廚五金', '其它五金'];
let catSel = null;
async function masterCatalog(b) {
  const cat = await api('/master/parts-catalog/full');
  const cats = Object.keys(cat).sort((x, y) => (CATEGORY_ORDER.indexOf(x) + 1 || 99) - (CATEGORY_ORDER.indexOf(y) + 1 || 99) || x.localeCompare(y));
  if (!catSel || !cat[catSel]) catSel = cats[0];
  const q = (b.querySelector('#catq')?.value || '').trim();
  const hits = q ? cats.flatMap((k) => cat[k].filter((x) => x.name.includes(q)).map((x) => ({ ...x, category: k }))) : null;
  const items = hits || cat[catSel].map((x) => ({ ...x, category: catSel }));
  const reload = async () => { state.catalog = null; await masterCatalog(b); };
  b.innerHTML = `
  <div class="split" style="grid-template-columns:220px 1fr">
    <aside>
      <div class="muted small" style="margin-bottom:6px">類別（依拆單順序）</div>
      <ul class="catlist">${cats.map((k) => `<li class="${k === catSel && !hits ? 'active' : ''}" data-cat="${esc(k)}">${esc(k)} <span class="muted">${cat[k].length}</span></li>`).join('')}</ul>
      <p class="muted small">五金放在「○○五金」類別，才不會算進板材片數。名稱會出現在料單的建議清單，類別自動判斷也靠這裡。</p>
    </aside>
    <div>
      <div class="row" style="justify-content:space-between">
        <h3 style="margin:0">${hits ? `搜尋「${esc(q)}」 <span class="muted small">(${items.length})</span>` : `${esc(catSel)} <span class="muted small">(${items.length})</span>`}</h3>
        <label>搜尋全部類別 <input id="catq" value="${esc(q)}" placeholder="輸入名稱關鍵字"></label>
      </div>
      <div class="row" style="margin:8px 0">
        <input id="catnew" placeholder="新名稱，例：美背" style="min-width:220px"> <button class="primary" id="catadd">加入「${esc(catSel)}」</button>
      </div>
      <div class="tablewrap"><table class="edit catitems">
        <tr><th style="width:40px">#</th><th>名稱（可直接改）</th>${hits ? '<th>類別</th>' : ''}<th>搬到類別</th><th style="width:150px"></th></tr>
        ${items.map((x, i) => `<tr data-id="${x.id}">
          <td class="muted">${i + 1}</td>
          <td><input name="name" value="${esc(x.name)}" style="min-width:220px"></td>
          ${hits ? `<td>${esc(x.category)}</td>` : ''}
          <td><select name="category">${opt(cats, x.category, false)}</select></td>
          <td class="nowrap">${hits ? '' : `<button class="link" data-move="up" title="上移">↑</button><button class="link" data-move="down" title="下移">↓</button>`}<button class="link danger" data-delcat="${x.id}">✕ 移除</button></td>
        </tr>`).join('') || `<tr><td colspan="5" class="muted">沒有項目</td></tr>`}
      </table></div>
    </div>
  </div>`;
  b.querySelectorAll('[data-cat]').forEach((li) => (li.onclick = () => { catSel = li.dataset.cat; b.querySelector('#catq').value = ''; masterCatalog(b); }));
  const qi = b.querySelector('#catq');
  qi.onkeydown = (e) => { if (e.key === 'Enter') masterCatalog(b); };
  qi.oninput = () => { clearTimeout(qi._t); qi._t = setTimeout(() => { const v = qi.value; masterCatalog(b).then(() => { const n = b.querySelector('#catq'); n.focus(); n.setSelectionRange(v.length, v.length); }); }, 350); };
  const add = async () => {
    const name = b.querySelector('#catnew').value.trim(); if (!name) return;
    try { await api('/master/parts-catalog', { method: 'POST', body: { category: catSel, name } }); toast('已加入'); reload(); } catch (err) { toast(err.message, true); }
  };
  b.querySelector('#catadd').onclick = add;
  b.querySelector('#catnew').onkeydown = (e) => { if (e.key === 'Enter') add(); };
  b.querySelectorAll('tr[data-id]').forEach((tr) => {
    const id = tr.dataset.id;
    tr.querySelector('input[name=name]').onchange = async (e) => { try { await api('/master/parts-catalog/' + id, { method: 'PUT', body: { name: e.target.value } }); toast('已改名'); state.catalog = null; } catch (err) { toast(err.message, true); } };
    tr.querySelector('input[name=name]').onkeydown = (e) => { if (e.key === 'Enter') e.target.blur(); };
    tr.querySelector('select[name=category]').onchange = async (e) => { try { await api('/master/parts-catalog/' + id, { method: 'PUT', body: { category: e.target.value } }); toast(`已搬到「${e.target.value}」`); reload(); } catch (err) { toast(err.message, true); } };
    tr.querySelectorAll('[data-move]').forEach((m) => (m.onclick = async () => { await api(`/master/parts-catalog/${id}/move`, { method: 'POST', body: { direction: m.dataset.move } }); reload(); }));
    tr.querySelector('[data-delcat]').onclick = async () => { if (!confirm('從目錄移除此名稱？（已在料單裡的板材不受影響）')) return; await api('/master/parts-catalog/' + id, { method: 'DELETE' }); reload(); };
  });
}
