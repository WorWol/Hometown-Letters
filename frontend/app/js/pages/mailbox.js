/* ================================================================
   故乡来信 · 信箱 (Mailbox)
   收件箱 / 发件箱 / 寄信 / 详情
   ================================================================ */

let _mboxTab = 'inbox';
let _mboxBusy = false;
let _mboxUnread = 0;

/* ================ MAIN RENDER ================ */

function renderMailbox() {
  const el = document.getElementById('page-mailbox');
  if (el) _renderMailboxCore(el);
}

function _renderMailboxCore(el) {
  const inboxActive = _mboxTab === 'inbox';
  el.innerHTML = `
    <div class="mailbox-grid">
      <section class="mailbox-list-panel paper-panel">
        <div class="panel-heading">
          <div>
            <span class="section-kicker" id="mbox-heading-kicker">${_mboxUnread > 0 ? _mboxUnread + ' UNREAD' : 'YOUR MAIL'}</span>
            <h2>${inboxActive ? '收件箱' : '发件箱'}</h2>
          </div>
          <div class="mailbox-tabs" role="tablist" aria-label="信箱分类">
            <button class="auth-tab ${inboxActive ? 'active' : ''}" id="mbox-inbox-tab" role="tab" aria-selected="${inboxActive}"
              onclick="_switchMailboxTab('inbox')">收件${_mboxUnread > 0 ? `<span class="mailbox-badge">${_mboxUnread}</span>` : ''}</button>
            <button class="auth-tab ${!inboxActive ? 'active' : ''}" role="tab" aria-selected="${!inboxActive}"
              onclick="_switchMailboxTab('outbox')">发件</button>
          </div>
        </div>
        <div class="mailbox-list" id="mailbox-list">
          <div class="visual-empty"><div><p>正在加载信箱…</p></div></div>
        </div>
      </section>
      <aside class="mailbox-side" aria-label="信箱操作与状态">
        <section class="dark-panel mailbox-compose-card">
          <span class="section-kicker">SEND A LETTER</span>
          <h3>给其他用户写信</h3>
          <p>输入对方的用户名，即可发送文字和附件。</p>
          <button class="btn btn-pri" onclick="_showComposeMail()">写一封信</button>
        </section>
        <section class="paper-panel mailbox-stats-card">
          <span class="section-kicker">MAILBOX STATUS</span>
          <h3>信箱状态</h3>
          <div class="stat-grid">
            <div><strong id="mbox-stat-unread">…</strong><span>未读</span></div>
            <div><strong id="mbox-stat-total">…</strong><span>总计</span></div>
          </div>
        </section>
      </aside>
    </div>`;
  _loadMailboxList();
}

/* ================ TAB SWITCH ================ */

function _switchMailboxTab(tab) {
  if (_mboxBusy) return;
  _mboxTab = tab;
  const el = document.getElementById('page-mailbox');
  if (el) _renderMailboxCore(el);
}

/* ================ LOAD ================ */

async function _loadMailboxList() {
  if (_mboxBusy) return;
  _mboxBusy = true;
  const listEl = document.getElementById('mailbox-list');
  if (!listEl) { _mboxBusy = false; return; }
  listEl.innerHTML = '<div class="visual-empty"><div><p>正在加载信件…</p></div></div>';

  try {
    if (_mboxTab === 'inbox') {
      const r = await api.getInbox(1, 30);
      if (r.ok && r.data) {
        _mboxUnread = r.data.unreadCount || 0;
        _renderMailList(listEl, (r.data.mails || []).map(mail => App.normalizeMail(mail)), 'inbox');
        _updateStats(r.data.unreadCount || 0, r.data.total || 0);
      } else {
        listEl.innerHTML = '<div class="visual-empty"><div><p>收件箱加载失败。</p><button class="btn btn-sec" onclick="_loadMailboxList()">重新加载</button></div></div>';
      }
    } else {
      const r = await api.getOutbox(1, 30);
      if (r.ok && r.data) {
        _renderMailList(listEl, (r.data.mails || []).map(mail => App.normalizeMail(mail)), 'outbox');
        _updateStats(0, r.data.total || 0);
      } else {
        listEl.innerHTML = '<div class="visual-empty"><div><p>发件箱加载失败。</p><button class="btn btn-sec" onclick="_loadMailboxList()">重新加载</button></div></div>';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<div class="visual-empty"><div><p>信箱加载失败，请检查网络。</p><button class="btn btn-sec" onclick="_loadMailboxList()">重新加载</button></div></div>';
  }
  _mboxBusy = false;
}

function _updateStats(unread, total) {
  const u = document.getElementById('mbox-stat-unread');
  const t = document.getElementById('mbox-stat-total');
  if (u) u.textContent = unread;
  if (t) t.textContent = total;
}

/* ================ RENDER LIST ================ */

function _renderMailList(container, mails, type) {
  if (!mails || !mails.length) {
    container.innerHTML = `
      <div class="visual-empty page-empty-scene mailbox-empty">
        <img src="assets/workbench/empty-mailbox-scene.webp" alt="清晨桌面上的乡间邮箱与待寄信件" onerror="this.closest('.page-empty-scene').classList.add('image-missing');this.remove()">
        <div>
          <h3>${type === 'inbox' ? '收件箱还是空的' : '还没有寄出过信'}</h3>
          <p>${type === 'inbox' ? '收到的用户来信会显示在这里。' : '你发送给其他用户的信会显示在这里。'}</p>
          <button class="btn btn-pri" onclick="_showComposeMail()">${type === 'inbox' ? '给其他用户写信' : '写第一封信'}</button>
        </div>
      </div>`;
    return;
  }

  const dateFmt = (ts) => {
    if (!ts) return '';
    return App.relativeTime(ts);
  };

  container.innerHTML = mails.map(m => `
    <button class="mailbox-item ${!m.isRead && type === 'inbox' ? 'unread' : ''}"
      onclick="_showMailDetail('${m.id}', '${type}', ${type === 'inbox' && !m.isRead})">
      <span class="mailbox-avatar">${(type === 'inbox' ? (m.senderUsername || '?') : (m.recipientUsername || '?'))[0]}</span>
      <span class="mailbox-body">
        <strong>${App._e(type === 'inbox' ? (m.senderUsername || '未知用户') : '发送给 ' + (m.recipientUsername || '未知用户'))}</strong>
        <small>${App._e(m.title || '无标题')}</small>
        <em>${App._e((m.content || '').slice(0, 60))}</em>
      </span>
      <span class="mailbox-meta">
        <time>${dateFmt(m.sentAt)}</time>
        ${m.attachedPostcard ? '<span>📮</span>' : ''}
        ${!m.isRead && type === 'inbox' ? '<span class="mailbox-dot"></span>' : ''}
      </span>
    </button>
  `).join('');
}

/* ================ MAIL DETAIL ================ */

async function _showMailDetail(mailId, type, unread = false) {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal workbench-modal';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = '<div class="modal-pnl paper-panel" style="max-width:520px;"><div class="modal-bd" style="text-align:center;padding:40px;">正在加载信件…</div></div>';
  document.body.appendChild(overlay);

  try {
    if (type === 'inbox' && unread) {
      const marked = await api.markMailRead(mailId).catch(() => null);
      if (marked?.ok) {
        _mboxUnread = Math.max(0, _mboxUnread - 1);
        _updateMailboxUnreadUI();
        void _loadMailboxList();
      }
    }
    const r = await api.getMailDetail(mailId);
    if (!r.ok || !r.data) {
      overlay.innerHTML = '<div class="modal-pnl paper-panel" style="max-width:400px;"><div class="modal-bd" style="text-align:center;padding:40px;"><p>没有找到这封信。</p><button class="btn btn-sec" onclick="this.closest(\'.modal\').remove()">关闭</button></div></div>';
      return;
    }
    const m = App.normalizeMail(r.data);
    const dateFmt = (ts) => ts ? new Date(ts).toLocaleString('zh-CN') : '';

    let attachHtml = '';
    if (m.attachedPostcard) {
      const pc = m.attachedPostcard;
      window._mailboxAttachedPostcard = pc;
      attachHtml = `
        <div class="mailbox-attach">
          <span class="section-kicker">ATTACHED POSTCARD</span>
          <button class="mailbox-attach-card with-media" onclick="App.showPostcardDetail(window._mailboxAttachedPostcard)">
            <span>${App._imgHtml(pc, { small: true })}</span><span><strong>${App._e(pc.title || '无题明信片')}</strong><small>${App._e(pc.place || '')}${pc.place && pc.mood ? ' · ' : ''}${App._e(pc.mood || '')}</small></span>
          </button>
        </div>`;
    }
    if (m.attachedLetter) {
      const lt = m.attachedLetter;
      attachHtml += `
        <div class="mailbox-attach">
          <span class="section-kicker">ATTACHED LETTER</span>
          <div class="mailbox-attach-card">
            <small>${App._e((lt.text || '').slice(0, 200))}</small>
          </div>
        </div>`;
    }

    overlay.innerHTML = `
      <div class="modal-pnl paper-panel" style="max-width:520px;">
        <div class="modal-hd">
          <div><span class="section-kicker">${type === 'inbox' ? 'FROM · ' + App._e(m.senderUsername || '未知用户') : 'TO · ' + App._e(m.recipientUsername || '未知用户')}</span>
          <h3>${App._e(m.title || '无标题')}</h3></div>
          <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
        </div>
        <div class="modal-meta">${dateFmt(m.sentAt)}</div>
        <div class="modal-bd" style="white-space:pre-wrap;">${App._e(m.content || '')}</div>
        ${attachHtml}
        <div class="modal-ft" style="display:flex;justify-content:space-between;align-items:center;">
          <button class="btn btn-dng" onclick="_deleteMailConfirm('${m.id}')">删除信件</button>
          <button class="btn btn-sec" onclick="this.closest('.modal').remove()">关闭</button>
        </div>
      </div>`;
    overlay.querySelector('.modal-cl')?.focus();
  } catch (e) {
    overlay.innerHTML = '<div class="modal-pnl paper-panel" style="max-width:400px;"><div class="modal-bd" style="text-align:center;padding:40px;"><p>信件加载失败，请稍后重试。</p><button class="btn btn-sec" onclick="this.closest(\'.modal\').remove()">关闭</button></div></div>';
  }
}

/* ================ DELETE ================ */

function _deleteMailConfirm(mailId) {
  const overlay = document.querySelector('.modal');
  if (!overlay) return;
  overlay.innerHTML = `
    <div class="modal-pnl paper-panel" style="max-width:360px;">
      <div class="modal-hd"><div><h3>删除这封信？</h3></div></div>
      <div class="modal-bd" style="text-align:center;padding:16px;"><p style="color:var(--ink-faint);">删除后，这封信将不再显示在你的信箱中。</p></div>
      <div class="modal-ft" style="display:flex;gap:8px;justify-content:center;">
        <button class="btn btn-dng" onclick="_doDeleteMail('${mailId}')">确认删除</button>
        <button class="btn btn-sec" onclick="this.closest('.modal').remove()">取消</button>
      </div>
    </div>`;
}

async function _doDeleteMail(mailId) {
  try {
    const r = await api.deleteMail(mailId);
    document.querySelector('.modal')?.remove();
    if (r.ok) {
      App.showToast('信件已删除');
      _loadMailboxList();
    } else {
      App.showToast(App.friendlyError(r.error, '删除失败，请稍后重试'), 3000);
    }
  } catch (e) { App.showToast(App.friendlyError(e, '删除失败，请稍后重试'), 3000); }
}

/* ================ COMPOSE ================ */

function _showComposeMail() {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal workbench-modal';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.onclick = e => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <div class="modal-pnl paper-panel" style="max-width:480px;">
      <div class="modal-hd">
        <div><span class="section-kicker">NEW LETTER</span><h3>给其他用户写信</h3></div>
        <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
      </div>
      <div class="mailbox-compose-form">
        <label>收件人
          <div class="mailbox-search-wrap">
            <input class="inp" id="compose-recipient" placeholder="输入用户名搜索" autocomplete="off"
              oninput="_searchRecipient(this.value)">
            <div class="mailbox-search-drop" id="compose-search-drop" style="display:none;"></div>
          </div>
        </label>
        <label>标题（可选）<input class="inp" id="compose-title" placeholder="输入标题"></label>
        <label>正文<textarea class="inp inp-ta" id="compose-content" rows="5" placeholder="输入信件内容"></textarea></label>
        <label>附带明信片（可选）
          <select class="inp" id="compose-postcard">
            <option value="">不附带</option>
            ${(App.state.postcards || []).map(pc => `<option value="${App._e(pc.id)}">${App._e(pc.title || '无题明信片')} · ${App._e(pc.place || '沿途')}</option>`).join('')}
          </select>
        </label>
        <label>附带历史信件（可选）
          <select class="inp" id="compose-letter">
            <option value="">不附带</option>
            ${(App.state.letters || []).map(lt => `<option value="${App._e(lt.id)}">${App._e((lt.text || '').slice(0, 28))}</option>`).join('')}
          </select>
        </label>
        <div class="setting-actions">
          <button class="btn btn-pri" onclick="_doSendMail()" id="compose-btn">发送信件</button>
          <span class="st" id="compose-status" aria-live="polite">&nbsp;</span>
        </div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#compose-recipient')?.focus();
}

let _searchTimer = null;

async function _searchRecipient(query) {
  clearTimeout(_searchTimer);
  const drop = document.getElementById('compose-search-drop');
  if (!drop) return;
  if (!query || query.trim().length < 1) { drop.style.display = 'none'; return; }

  _searchTimer = setTimeout(async () => {
    try {
      const r = await api.lookupUsers(query.trim());
      if (!r.ok || !r.data || !r.data.users?.length) {
        drop.innerHTML = '<div class="mailbox-search-item" style="color:var(--ink-faint);">没有找到匹配的用户</div>';
        drop.style.display = 'block';
        return;
      }
      drop.innerHTML = r.data.users.map(u => `
        <button type="button" class="mailbox-search-item" onclick='_selectRecipient(${App._js(u.username)})'>
          <span class="mailbox-search-avatar">${u.username[0]}</span> ${App._e(u.username)}
        </button>
      `).join('');
      drop.style.display = 'block';
    } catch (e) {
      drop.innerHTML = '<div class="mailbox-search-item" style="color:var(--ink-faint);">搜索失败，请稍后重试。</div>';
      drop.style.display = 'block';
    }
  }, 300);
}

function _selectRecipient(username) {
  const inp = document.getElementById('compose-recipient');
  const drop = document.getElementById('compose-search-drop');
  if (inp) inp.value = username;
  if (drop) drop.style.display = 'none';
}

async function _doSendMail() {
  const recipient = document.getElementById('compose-recipient');
  const title = document.getElementById('compose-title');
  const content = document.getElementById('compose-content');
  const postcard = document.getElementById('compose-postcard');
  const letter = document.getElementById('compose-letter');
  const btn = document.getElementById('compose-btn');
  const status = document.getElementById('compose-status');
  const u = recipient?.value?.trim();
  const c = content?.value?.trim();
  if (!u) { if (status) status.textContent = '请输入收件人用户名'; return; }
  if (!c) { if (status) status.textContent = '请输入信件正文'; return; }
  if (btn) btn.disabled = true;
  if (status) status.textContent = '正在发送…';
  try {
    const postcardId = postcard?.value ? Number(String(postcard.value).replace(/^pc-/, '')) : null;
    const letterId = letter?.value ? Number(String(letter.value).replace(/^ltr-/, '')) : null;
    const r = await api.sendMail(u, title?.value?.trim() || '', c, postcardId, letterId);
    if (r.ok) {
      document.querySelector('.modal')?.remove();
      App.showToast('信件已发送');
      _mboxTab = 'outbox';
      const page = document.getElementById('page-mailbox');
      if (page) _renderMailboxCore(page);
    } else {
      if (status) status.textContent = App.friendlyError(r.error, '发送失败，请稍后重试');
    }
  } catch (e) { if (status) status.textContent = App.friendlyError(e, '发送失败，请稍后重试'); }
  if (btn) btn.disabled = false;
}

function _updateMailboxUnreadUI() {
  const kicker = document.getElementById('mbox-heading-kicker');
  const tab = document.getElementById('mbox-inbox-tab');
  if (kicker) kicker.textContent = _mboxUnread > 0 ? `${_mboxUnread} UNREAD` : 'YOUR MAIL';
  if (tab) {
    tab.innerHTML = `收件${_mboxUnread > 0 ? `<span class="mailbox-badge">${_mboxUnread}</span>` : ''}`;
  }
}

document.addEventListener('click', function(e) {
  const drop = document.getElementById('compose-search-drop');
  if (drop && !e.target.closest('#compose-recipient') && !e.target.closest('#compose-search-drop')) {
    drop.style.display = 'none';
  }
});
