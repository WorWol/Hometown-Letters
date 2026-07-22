(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (value) => String(value ?? '').replace(/[&<>"']/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const bytes = (value) => { let n = Number(value || 0); if (!n) return '—'; const units = ['B','KB','MB','GB','TB']; let i = 0; while (n >= 1024 && i < units.length - 1) { n /= 1024; i += 1; } return `${n.toFixed(i ? 1 : 0)} ${units[i]}`; };
  const percent = (value) => value == null ? '—' : `${Number(value).toFixed(1)}%`;
  let token = localStorage.getItem('hometown_developer_token') || '';
  let schema = {};
  let offset = 0;
  const limit = 50;

  const developerUsername = localStorage.getItem('hometown_developer_username') || '';
  if (!token) {
    window.location.replace('/admin/admin-login.html');
    return;
  }
  $('account-name').textContent = developerUsername || 'Developer';
  $('account-avatar').textContent = (developerUsername[0] || 'D').toUpperCase();
  const headers = () => token ? {'Authorization': `Bearer ${token}`} : {};
  const status = (message, kind = 'muted') => { $('status').textContent = message; $('status').className = kind; };
  async function request(path, options = {}) {
    const response = await fetch(path, {headers: {...headers(), ...(options.headers || {})}, ...options});
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(response.status === 401 ? '开发者账号认证失败，请重新登录' : payload.detail || '请求失败');
    return payload.data;
  }
  const metric = (label, value, note = '') => `<div class="metric"><span>${esc(label)}</span><strong>${esc(value)}</strong><em>${esc(note)}</em></div>`;
  const runtimeHtml = (data) => {
    const container = data.containerMemory || {};
    return `<div class="resource-row"><span>CPU 使用率</span><strong>${percent(data.cpu?.usagePercent)}</strong></div>
      <div><div class="resource-row"><span>系统内存</span><strong>${bytes(data.systemMemory?.used)} / ${bytes(data.systemMemory?.total)}</strong></div><div class="bar"><i style="width:${Math.min(100, data.systemMemory?.usagePercent || 0)}%"></i></div></div>
      <div class="resource-row"><span>Python 进程 RSS</span><strong>${bytes(data.process?.rss)} (${percent(data.process?.memoryPercent)})</strong></div>
      <div><div class="resource-row"><span>Docker 容器内存</span><strong>${container.available ? `${bytes(container.used)} / ${bytes(container.limit)}` : '非容器环境'}</strong></div>${container.available ? `<div class="bar"><i style="width:${Math.min(100, container.usagePercent || 0)}%"></i></div>` : ''}</div>
      <div class="resource-row"><span>磁盘</span><strong>${bytes(data.disk?.used)} / ${bytes(data.disk?.total)} (${percent(data.disk?.usagePercent)})</strong></div>`;
  };

  async function loadOverview() {
    const data = await request('/api/admin/overview');
    $('overview-metrics').innerHTML = [metric('用户', data.users), metric('信件', data.letters), metric('明信片', data.postcards), metric('今日错误', data.errorsToday), metric('磁盘已用', bytes(data.disk.used), data.storageBackend)].join('');
    $('overview-runtime').innerHTML = runtimeHtml(data.runtime);
    const events = await request('/api/admin/events?limit=6');
    $('overview-events').innerHTML = events.length ? events.map((event) => `<p class="event-line"><span class="badge ${event.level === 'error' ? 'bad' : ''}">${esc(event.level)}</span> ${esc(event.eventType)}<br><span class="muted">${esc(event.message || '')} · ${esc(new Date(event.createdAt).toLocaleString())}</span></p>`).join('') : '<p class="muted">暂无事件</p>';
  }
  async function loadMetrics() {
    const data = await request('/api/admin/metrics');
    $('metrics-summary').textContent = `累计记录 ${data.total.count} 次 API 调用，数据保存在数据库，重启后不会清零。`;
    $('metrics-table').innerHTML = data.routes.length ? data.routes.map((row) => `<tr><td>${esc(row.method)}</td><td><code>${esc(row.path)}</code></td><td>${row.count}</td><td>${row.success}</td><td>${row.clientErrors}</td><td>${row.serverErrors}</td><td>${row.averageMs} ms</td><td>${row.maxMs} ms</td></tr>`).join('') : '<tr><td colspan="8" class="muted">暂无 API 调用</td></tr>';
  }
  async function loadRuntime() { $('runtime-detail').innerHTML = runtimeHtml(await request('/api/admin/runtime')); }
  async function loadPostcards() {
    const query = encodeURIComponent($('pc-query').value.trim());
    const data = await request(`/api/admin/postcards?q=${query}&limit=200`);
    $('postcards-table').innerHTML = data.items.length ? data.items.map((row) => { const tracked = Object.keys(row.ossStatus || {}).filter((key) => row.imageKeys?.[key]); const complete = tracked.length > 0 && tracked.every((key) => row.ossStatus[key]); return `<tr><td>${row.id}</td><td>${row.userId}</td><td>${esc(row.title || '无题')}</td><td>${esc(row.place || '')}</td><td>${esc(new Date(row.createdAt).toLocaleString())}</td><td><span class="badge ${complete ? 'good' : 'bad'}">${complete ? '完整' : '缺失'}</span></td><td><button class="secondary" data-action="view-postcard" data-id="${row.id}">详情</button> <button class="secondary" data-action="edit-postcard" data-id="${row.id}">编辑</button> <button class="danger" data-action="delete-postcard" data-id="${row.id}">删除</button></td></tr>`; }).join('') : '<tr><td colspan="7" class="muted">没有符合条件的明信片</td></tr>';
  }
  async function viewPostcard(id) {
    const row = await request(`/api/admin/postcards/${id}`);
    const image = (key, label) => row.imageUrls?.[key] ? `<figure><img src="${esc(row.imageUrls[key])}" alt="${esc(label)}"><figcaption>${esc(label)} · ${row.ossStatus?.[key] ? 'OSS 已找到' : 'OSS 缺失'}</figcaption></figure>` : `<figure><div class="image-error">暂无图片</div><figcaption>${esc(label)}</figcaption></figure>`;
    $('modal-root').innerHTML = `<div class="modal" data-close-modal><div class="modal-card"><div class="modal-head"><h2>明信片详情 #${row.id}</h2><button class="close" data-action="close-modal">×</button></div><div class="preview-grid">${image('reference','参考图')}${image('thumb','缩略图')}${image('card','卡片图')}${image('original','原图')}</div><div class="form-grid"><label>信件地点<input value="${esc(row.place)}" readonly></label><label>画面取景<input value="${esc(row.generationPlace)}" readonly></label><label>标题<input value="${esc(row.title)}" readonly></label><label>情绪<input value="${esc(row.mood)}" readonly></label><label>标签<input value="${esc((row.tags || []).join('、'))}" readonly></label><label class="full">正文<textarea readonly>${esc(row.body)}</textarea></label><label class="full">诗歌<textarea readonly>${esc(row.poem)}</textarea></label></div><div class="modal-actions"><button class="secondary" data-action="close-modal">关闭</button></div></div></div>`;
  }
  async function editPostcard(id) {
    const row = await request(`/api/admin/postcards/${id}`);
    $('modal-root').innerHTML = `<div class="modal"><form class="modal-card" id="edit-form"><div class="modal-head"><h2>编辑明信片 #${row.id}</h2><button type="button" class="close" data-action="close-modal">×</button></div><div class="form-grid"><label>标题<input name="title" value="${esc(row.title)}"></label><label>地点<input name="place" value="${esc(row.place)}"></label><label>情绪<input name="mood" value="${esc(row.mood)}"></label><label>标签<input name="tags" value="${esc((row.tags || []).join(','))}"></label><label class="full">正文<textarea name="body">${esc(row.body)}</textarea></label><label class="full">诗歌<textarea name="poem">${esc(row.poem)}</textarea></label></div><div class="modal-actions"><button type="button" class="secondary" data-action="close-modal">取消</button><button class="primary">保存修改</button></div></form></div>`;
    $('edit-form').onsubmit = async (event) => { event.preventDefault(); const form = new FormData(event.target); const body = {title: form.get('title'), place: form.get('place'), mood: form.get('mood'), body: form.get('body'), poem: form.get('poem'), tags: String(form.get('tags') || '').split(',').map((value) => value.trim()).filter(Boolean)}; await request(`/api/admin/postcards/${id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)}); closeModal(); status('明信片已更新', 'ok'); loadPostcards(); };
  }
  async function deletePostcard(id) { if (!confirm('确定删除这张明信片以及 OSS 中的图片吗？此操作不可恢复。')) return; await request(`/api/admin/postcards/${id}`, {method: 'DELETE'}); status(`明信片 #${id} 已删除`, 'ok'); loadPostcards(); }
  async function loadStorageTasks() { const data = await request('/api/admin/storage/tasks?status=pending'); $('storage-tasks-table').innerHTML = data.length ? data.map((row) => `<tr><td>${row.id}</td><td>${esc(`${row.entityType} #${row.entityId}`)}</td><td><span class="badge ${row.status === 'completed' ? 'good' : row.status === 'failed' ? 'bad' : ''}">${esc(row.status)}</span></td><td>${row.attempts}</td><td>${esc(row.lastError || '—')}</td><td>${esc(new Date(row.updatedAt).toLocaleString())}</td></tr>`).join('') : '<tr><td colspan="6" class="muted">暂无待处理任务</td></tr>'; }
  async function loadStorage() {
    const data = await request('/api/admin/storage/check');
    const cell = (row, key) => {
      if (!row.keys?.[key]) return '<td><span class="badge">未记录</span></td>';
      const p = row.present?.[key];
      const cls = p === true ? 'good' : p === false ? 'bad' : 'warn';
      const text = p === true ? '存在' : p === false ? '缺失' : '失败';
      return `<td><span class="badge ${cls}">${text}</span></td>`;
    };
    const summary = (c) => c === true ? '<span class="badge good">一致</span>' : c === false ? '<span class="badge bad">不一致</span>' : '<span class="badge warn">无法判定</span>';
    $('storage-table').innerHTML = data.items.length ? data.items.map((row) => `<tr><td>${row.postcardId}</td>${['reference','thumb','card','original'].map((key) => cell(row, key)).join('')}<td>${summary(row.complete)}</td></tr>`).join('') : '<tr><td colspan="6" class="muted">暂无数据</td></tr>';
    await loadStorageTasks();
  }
  async function retryStorageTasks() { const data = await request('/api/admin/storage/tasks/retry', {method: 'POST'}); status(`已完成 ${data.completed} 个 OSS 删除任务`, 'ok'); await loadStorageTasks(); }
  async function loadEvents() { const data = await request('/api/admin/events?limit=300'); $('events-table').innerHTML = data.length ? data.map((row) => `<tr><td>${esc(new Date(row.createdAt).toLocaleString())}</td><td><span class="badge ${row.level === 'error' || row.level === 'warning' ? 'bad' : ''}">${esc(row.level)}</span></td><td>${esc(row.eventType)}</td><td>${esc(row.message)}</td><td>${esc(row.userId || '-')}</td></tr>`).join('') : '<tr><td colspan="5" class="muted">暂无事件</td></tr>'; }
  async function loadLogs() { const data = await request('/api/admin/logs?limit=300'); $('logs').textContent = data.lines.length ? data.lines.join('\n') : '暂无日志'; }

  async function loadStyles() {
    const data = await request('/api/admin/styles');
    $('styles-table').innerHTML = data.length ? data.map((row) => `<tr><td><code>${esc(row.styleId)}</code></td><td>${esc(row.label)}</td><td><code>${esc(row.analysisHint || '-')}</code></td><td>${row.sortOrder}</td><td><span class="badge ${row.isActive ? 'good' : 'bad'}">${row.isActive ? '启用' : '下架'}</span></td><td>${row.isSystem ? '<span class="badge">内置</span>' : '<span class="badge">自定义</span>'}</td><td><button class="secondary" data-action="edit-style" data-id="${esc(row.styleId)}">编辑</button> <button class="secondary" data-action="toggle-style" data-id="${esc(row.styleId)}" data-active="${row.isActive}">${row.isActive ? '下架' : '启用'}</button>${row.isSystem ? '' : ` <button class="danger" data-action="delete-style" data-id="${esc(row.styleId)}">删除</button>`}</td></tr>`).join('') : '<tr><td colspan="7" class="muted">暂无风格</td></tr>';
  }
  function styleForm(row) {
    const creating = !row.styleId;
    return `<div class="modal"><form class="modal-card" id="style-form"><div class="modal-head"><h2>${creating ? '新增' : '编辑'}图像风格</h2><button type="button" class="close" data-action="close-modal">×</button></div><div class="form-grid"><label>风格标识（英文，唯一）<input name="style_id" value="${esc(row.styleId || '')}" ${creating ? 'required placeholder="如 cyberpunk"' : 'readonly'}></label><label>显示名称<input name="label" value="${esc(row.label || '')}" required></label><label class="full">风格提示词（追加到生图 prompt 末尾）<textarea name="style_prompt" required>${esc(row.stylePrompt || '')}</textarea></label><label class="full">分析提示（注入信件分析的 {STYLE_HINT}）<textarea name="analysis_hint">${esc(row.analysisHint || '')}</textarea></label><label>排序<input name="sort_order" type="number" value="${row.sortOrder ?? 0}"></label></div><div class="modal-actions"><button type="button" class="secondary" data-action="close-modal">取消</button><button class="primary">保存</button></div></form></div>`;
  }
  async function createStyle() { $('modal-root').innerHTML = styleForm({}); bindStyleForm(null); }
  async function editStyle(styleId) { const data = await request('/api/admin/styles'); const row = data.find((s) => s.styleId === styleId); if (!row) return status('风格不存在', 'error'); $('modal-root').innerHTML = styleForm(row); bindStyleForm(styleId); }
  function bindStyleForm(styleId) {
    $('style-form').onsubmit = async (event) => {
      event.preventDefault();
      const form = new FormData(event.target);
      const body = {label: form.get('label'), style_prompt: form.get('style_prompt'), analysis_hint: form.get('analysis_hint') || '', sort_order: Number(form.get('sort_order') || 0)};
      if (styleId) {
        await request(`/api/admin/styles/${encodeURIComponent(styleId)}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        status('风格已更新', 'ok');
      } else {
        body.style_id = form.get('style_id');
        await request('/api/admin/styles', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
        status('风格已新增', 'ok');
      }
      closeModal(); loadStyles();
    };
  }
  async function deleteStyle(styleId) { if (!confirm('确定删除这个自定义风格吗？已设置该风格的用户将回退到默认风格。')) return; await request(`/api/admin/styles/${encodeURIComponent(styleId)}`, {method: 'DELETE'}); status('风格已删除', 'ok'); loadStyles(); }
  async function toggleStyle(styleId, active) { await request(`/api/admin/styles/${encodeURIComponent(styleId)}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({is_active: !active})}); status(active ? '风格已下架' : '风格已启用', 'ok'); loadStyles(); }

  async function loadPrompts() {
    const data = await request('/api/admin/prompts');
    $('prompts-table').innerHTML = data.length ? data.map((row) => `<tr><td><code>${esc(row.key)}</code></td><td>${esc(row.label)}</td><td>${esc(row.description || '')}</td><td><span class="badge ${row.overridden ? 'good' : ''}">${row.overridden ? '已覆盖' : '默认'}</span></td><td><button class="secondary" data-action="edit-prompt" data-key="${esc(row.key)}">编辑</button>${row.overridden ? ` <button class="danger" data-action="reset-prompt" data-key="${esc(row.key)}">重置</button>` : ''}</td></tr>`).join('') : '<tr><td colspan="5" class="muted">暂无提示词</td></tr>';
  }
  async function editPrompt(key) {
    const data = await request('/api/admin/prompts');
    const row = data.find((p) => p.key === key);
    if (!row) return status('提示词不存在', 'error');
    $('modal-root').innerHTML = `<div class="modal"><form class="modal-card" id="prompt-form"><div class="modal-head"><h2>编辑提示词 · ${esc(row.label)}</h2><button type="button" class="close" data-action="close-modal">×</button></div><p class="muted">${esc(row.description || '')}</p><details style="margin:10px 0"><summary class="muted">查看默认值</summary><pre>${esc(row.defaultContent)}</pre></details><label class="full" style="margin-top:13px">覆盖内容<textarea name="content" class="json-field" required>${esc(row.content)}</textarea></label><div class="modal-actions"><button type="button" class="secondary" data-action="close-modal">取消</button><button class="primary">保存</button></div></form></div>`;
    $('prompt-form').onsubmit = async (event) => { event.preventDefault(); const form = new FormData(event.target); await request(`/api/admin/prompts/${encodeURIComponent(key)}`, {method: 'PUT', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({content: form.get('content')})}); closeModal(); status('提示词已更新', 'ok'); loadPrompts(); };
  }
  async function resetPrompt(key) { if (!confirm('确定重置该提示词为默认值吗？')) return; await request(`/api/admin/prompts/${encodeURIComponent(key)}`, {method: 'DELETE'}); status('提示词已重置', 'ok'); loadPrompts(); }

  function inputFor(field, value, creating) { const current = value == null ? '' : value; if (field.name === 'password') return `<input data-field="password" type="password" minlength="8" maxlength="72" placeholder="${creating ? '至少 8 个字符' : '留空表示不修改'}" ${creating ? 'required' : ''}>`; if (field.type === 'boolean') return `<input type="checkbox" data-field="${esc(field.name)}" ${current ? 'checked' : ''}>`; if (field.type === 'json') return `<textarea class="json-field" data-field="${esc(field.name)}">${esc(JSON.stringify(current || [], null, 2))}</textarea>`; return `<input data-field="${esc(field.name)}" type="${field.type === 'integer' ? 'number' : field.type === 'datetime' ? 'datetime-local' : 'text'}" value="${esc(field.type === 'datetime' && current ? String(current).slice(0, 16) : current)}">`; }
  function rowPayload(form) { const payload = {}; form.querySelectorAll('[data-field]').forEach((input) => { const name = input.dataset.field; if (input.type === 'checkbox') payload[name] = input.checked; else if (input.classList.contains('json-field')) payload[name] = JSON.parse(input.value || 'null'); else if (input.type === 'number') payload[name] = input.value === '' ? null : Number(input.value); else payload[name] = input.value; }); return payload; }
  function rowForm(table, row, creating) { let fields = schema[table].fields.filter((field) => field.writable && !field.secret && field.name !== 'id'); if (table === 'users') fields = [...fields, {name: 'password', type: 'string'}]; return `<div class="modal"><form class="modal-card" id="db-form"><div class="modal-head"><h2>${creating ? '新增' : '编辑'} ${esc(table)}</h2><button type="button" class="close" data-action="close-modal">×</button></div><div class="form-grid">${fields.map((field) => `<label class="${field.type === 'json' ? 'full' : ''}">${esc(field.name)}${inputFor(field, row[field.name], creating)}</label>`).join('')}</div><div class="modal-actions"><button type="button" class="secondary" data-action="close-modal">取消</button><button class="primary">保存</button></div></form></div>`; }
  async function ensureSchema() { if (Object.keys(schema).length) return; schema = await request('/api/admin/schema'); $('db-table').innerHTML = Object.keys(schema).map((name) => `<option value="${esc(name)}">${esc(name)}</option>`).join(''); }
  async function loadDatabase() { await ensureSchema(); const table = $('db-table').value; const query = encodeURIComponent($('db-query').value.trim()); const data = await request(`/api/admin/data/${encodeURIComponent(table)}?q=${query}&limit=${limit}&offset=${offset}`); const fields = schema[table].fields.filter((field) => !field.secret); const readOnly = table === 'system_events'; $('database-head').innerHTML = `<tr>${fields.map((field) => `<th>${esc(field.name)}</th>`).join('')}${readOnly ? '' : '<th>操作</th>'}</tr>`; $('database-table').innerHTML = data.items.length ? data.items.map((row) => `<tr>${fields.map((field) => `<td>${esc(field.type === 'json' ? JSON.stringify(row[field.name]) : row[field.name] ?? '—')}</td>`).join('')}${readOnly ? '' : `<td><button class="secondary" data-action="edit-row" data-table="${esc(table)}" data-id="${row.id}">编辑</button> <button class="danger" data-action="delete-row" data-table="${esc(table)}" data-id="${row.id}">删除</button></td>`}</tr>`).join('') : `<tr><td colspan="${fields.length + (readOnly ? 0 : 1)}" class="muted">当前表没有数据</td></tr>`; $('db-summary').textContent = `${table} · 共 ${data.total} 条；敏感字段和系统事件受保护。`; $('db-page').textContent = `${data.total ? offset + 1 : 0}–${Math.min(offset + data.items.length, data.total)} / ${data.total}`; $('db-prev').disabled = offset === 0; $('db-next').disabled = offset + data.items.length >= data.total; }
  async function createRow() { await ensureSchema(); const table = $('db-table').value; $('modal-root').innerHTML = rowForm(table, {}, true); $('db-form').onsubmit = async (event) => { event.preventDefault(); await request(`/api/admin/data/${encodeURIComponent(table)}`, {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(rowPayload(event.target))}); closeModal(); status('数据已新增', 'ok'); offset = 0; loadDatabase(); }; }
  async function editRow(table, id) { const row = await request(`/api/admin/data/${encodeURIComponent(table)}/${id}`); $('modal-root').innerHTML = rowForm(table, row, false); $('db-form').onsubmit = async (event) => { event.preventDefault(); await request(`/api/admin/data/${encodeURIComponent(table)}/${id}`, {method: 'PATCH', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(rowPayload(event.target))}); closeModal(); status('数据已更新', 'ok'); loadDatabase(); }; }
  async function deleteRow(table, id) { if (!confirm(`确定删除 ${table} #${id} 吗？涉及 OSS 的明信片会同时清理图片。`)) return; await request(`/api/admin/data/${encodeURIComponent(table)}/${id}`, {method: 'DELETE'}); status('数据已删除', 'ok'); loadDatabase(); }
  function closeModal() { $('modal-root').innerHTML = ''; }
  function switchView(name) { document.querySelectorAll('.view').forEach((node) => node.classList.toggle('active', node.id === `view-${name}`)); document.querySelectorAll('nav button').forEach((node) => node.classList.toggle('active', node.dataset.view === name)); $('page-title').textContent = {overview:'系统概览', metrics:'API 监控', runtime:'服务器资源', postcards:'明信片管理', styles:'图像风格', prompts:'提示词', database:'数据库', storage:'OSS 检查', events:'事件与日志'}[name]; const loaders = {overview: loadOverview, metrics: loadMetrics, runtime: loadRuntime, postcards: loadPostcards, styles: loadStyles, prompts: loadPrompts, database: loadDatabase, storage: loadStorage, events: () => Promise.all([loadEvents(), loadLogs()])}; if (loaders[name]) loaders[name]().catch((error) => status(error.message, 'error')); }
  document.addEventListener('click', (event) => { const target = event.target.closest('[data-action],[data-view-target],nav button'); if (!target) return; if (target.dataset.viewTarget) return switchView(target.dataset.viewTarget); if (target.dataset.view) return switchView(target.dataset.view); const action = target.dataset.action; const actions = {'refresh-overview': loadOverview, 'refresh-metrics': loadMetrics, 'refresh-runtime': loadRuntime, 'search-postcards': loadPostcards, 'load-database': loadDatabase, 'create-row': createRow, 'load-storage': loadStorage, 'load-storage-tasks': loadStorageTasks, 'retry-storage-tasks': retryStorageTasks, 'load-events': loadEvents, 'load-logs': loadLogs, 'close-modal': closeModal, 'view-postcard': () => viewPostcard(target.dataset.id), 'edit-postcard': () => editPostcard(target.dataset.id), 'delete-postcard': () => deletePostcard(target.dataset.id), 'edit-row': () => editRow(target.dataset.table, target.dataset.id), 'delete-row': () => deleteRow(target.dataset.table, target.dataset.id), 'create-style': createStyle, 'edit-style': () => editStyle(target.dataset.id), 'delete-style': () => deleteStyle(target.dataset.id), 'toggle-style': () => toggleStyle(target.dataset.id, target.dataset.active === 'true'), 'refresh-prompts': loadPrompts, 'edit-prompt': () => editPrompt(target.dataset.key), 'reset-prompt': () => resetPrompt(target.dataset.key)}; if (actions[action]) actions[action]().catch((error) => status(error.message, 'error')); });
  $('db-prev').onclick = () => { offset = Math.max(0, offset - limit); loadDatabase().catch((error) => status(error.message, 'error')); };
  $('db-next').onclick = () => { offset += limit; loadDatabase().catch((error) => status(error.message, 'error')); };
  document.querySelector('[data-action="developer-logout"]').onclick = () => { token = ''; localStorage.removeItem('hometown_developer_token'); window.location.replace('/admin/admin-login.html'); };
  loadOverview().catch((error) => { if (error.message.includes('认证失败')) window.location.replace('/admin/admin-login.html'); else status(error.message, 'error'); });
})();
