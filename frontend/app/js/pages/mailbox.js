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
          <div class="mailbox-tabs" role="tablist">
            <button class="auth-tab ${inboxActive ? 'active' : ''}" id="mbox-inbox-tab" role="tab" aria-selected="${inboxActive}"
              onclick="_switchMailboxTab('inbox')">收件${_mboxUnread > 0 ? `<span class="mailbox-badge">${_mboxUnread}</span>` : ''}</button>
            <button class="auth-tab ${!inboxActive ? 'active' : ''}" role="tab" aria-selected="${!inboxActive}"
              onclick="_switchMailboxTab('outbox')">发件</button>
          </div>
        </div>
        <div class="mailbox-list" id="mailbox-list">
          <div class="visual-empty"><div><p>加载中……</p></div></div>
        </div>
      </section>
      <aside class="mailbox-side" aria-label="信箱操作与状态">
        <section class="dark-panel mailbox-compose-card">
          <span class="section-kicker">SEND A LETTER</span>
          <h3>寄出一封信</h3>
          <p>把想说的话装在信封里，寄给另一位同样在回望故乡的人。</p>
          <button class="btn btn-pri" onclick="_showComposeMail()">✉ 写一封信</button>
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
  listEl.innerHTML = '<div class="visual-empty"><div><p>正在翻开信箱……</p></div></div>';

  try {
    if (_mboxTab === 'inbox') {
      const r = await api.getInbox(1, 30);
      if (r.ok && r.data) {
        _mboxUnread = r.data.unreadCount || 0;
        _renderMailList(listEl, (r.data.mails || []).map(mail => App.normalizeMail(mail)), 'inbox');
        _updateStats(r.data.unreadCount || 0, r.data.total || 0);
      } else {
        listEl.innerHTML = '<div class="visual-empty"><div><p>暂时无法打开收件箱。</p></div></div>';
      }
    } else {
      const r = await api.getOutbox(1, 30);
      if (r.ok && r.data) {
        _renderMailList(listEl, (r.data.mails || []).map(mail => App.normalizeMail(mail)), 'outbox');
        _updateStats(0, r.data.total || 0);
      } else {
        listEl.innerHTML = '<div class="visual-empty"><div><p>暂时无法打开发件箱。</p></div></div>';
      }
    }
  } catch (e) {
    listEl.innerHTML = '<div class="visual-empty"><div><p>信箱暂时打不开，检查一下网络吧。</p></div></div>';
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
          <p>${type === 'inbox' ? '还没有人给你寄信，或者给自己写一封吧。' : '把第一封信寄出去，它会沿着邮路抵达另一个人的故乡。'}</p>
          <button class="btn btn-pri" onclick="_showComposeMail()">${type === 'inbox' ? '写一封信' : '寄出第一封'}</button>
        </div>
      </div>`;
    return;
  }

  const dateFmt = (ts) => {
    if (!ts) return '';
    const d = new Date(ts), now = new Date(), diff = now - d;
    if (diff < 3600000) return `${Math.floor(diff / 60000)}分钟前`;
    if (diff < 86400000) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
    return d.toLocaleDateString('zh-CN');
  };

  container.innerHTML = mails.map(m => `
    <button class="mailbox-item ${!m.isRead && type === 'inbox' ? 'unread' : ''}"
      onclick="_showMailDetail('${m.id}', '${type}', ${type === 'inbox' && !m.isRead})">
      <span class="mailbox-avatar">${(type === 'inbox' ? (m.senderUsername || '?') : (m.recipientUsername || '?'))[0]}</span>
      <span class="mailbox-body">
        <strong>${App._e(type === 'inbox' ? (m.senderUsername || '远方来信') : '寄给 ' + App._e(m.recipientUsername || '远方的谁'))}</strong>
        <small>${App._e(m.title || '(没有标题)')}</small>
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
  overlay.innerHTML = '<div class="modal-pnl paper-panel" style="max-width:520px;"><div class="modal-bd" style="text-align:center;padding:40px;">正在展开信纸……</div></div>';
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
      overlay.innerHTML = '<div class="modal-pnl paper-panel" style="max-width:400px;"><div class="modal-bd" style="text-align:center;padding:40px;"><p>这封信找不到了。</p><button class="btn btn-sec" onclick="this.closest(\'.modal\').remove()">关上信箱</button></div></div>';
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
          <div><span class="section-kicker">${type === 'inbox' ? 'FROM · ' + App._e(m.senderUsername || '远方') : 'TO · ' + App._e(m.recipientUsername || '远方')}</span>
          <h3>${App._e(m.title || '一封没有标题的信')}</h3></div>
          <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
        </div>
        <div class="modal-meta">${dateFmt(m.sentAt)}</div>
        <div class="modal-bd" style="white-space:pre-wrap;">${App._e(m.content || '')}</div>
        ${attachHtml}
        <div class="modal-ft" style="display:flex;justify-content:space-between;align-items:center;">
          <button class="btn btn-dng" onclick="_deleteMailConfirm('${m.id}')">删除这封信</button>
          <button class="btn btn-sec" onclick="this.closest('.modal').remove()">收好信纸</button>
        </div>
      </div>`;
    overlay.querySelector('.modal-cl')?.focus();
  } catch (e) {
    overlay.innerHTML = '<div class="modal-pnl paper-panel" style="max-width:400px;"><div class="modal-bd" style="text-align:center;padding:40px;"><p>打开信封时出了点问题。</p><button class="btn btn-sec" onclick="this.closest(\'.modal\').remove()">关上信箱</button></div></div>';
  }
}

/* ================ DELETE ================ */

function _deleteMailConfirm(mailId) {
  const overlay = document.querySelector('.modal');
  if (!overlay) return;
  overlay.innerHTML = `
    <div class="modal-pnl paper-panel" style="max-width:360px;">
      <div class="modal-hd"><div><h3>丢掉这封信？</h3></div></div>
      <div class="modal-bd" style="text-align:center;padding:16px;"><p style="color:var(--ink-faint);">丢掉之后，它不会在你这边留下了。</p></div>
      <div class="modal-ft" style="display:flex;gap:8px;justify-content:center;">
        <button class="btn btn-dng" onclick="_doDeleteMail('${mailId}')">丢掉</button>
        <button class="btn btn-sec" onclick="this.closest('.modal').remove()">再留一会儿</button>
      </div>
    </div>`;
}

async function _doDeleteMail(mailId) {
  try {
    const r = await api.deleteMail(mailId);
    document.querySelector('.modal')?.remove();
    if (r.ok) {
      App.showToast('信件已经丢掉了');
      _loadMailboxList();
    } else {
      App.showToast('没丢掉: ' + (r.error || '再试一次'), 3000);
    }
  } catch (e) { App.showToast('网络不好，再试一次', 3000); }
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
        <div><span class="section-kicker">NEW LETTER</span><h3>✉ 写一封信</h3></div>
        <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
      </div>
      <div class="mailbox-compose-form">
        <label>收件人是谁？
          <div class="mailbox-search-wrap">
            <input class="inp" id="compose-recipient" placeholder="输入用户名搜索……" autocomplete="off"
              oninput="_searchRecipient(this.value)">
            <div class="mailbox-search-drop" id="compose-search-drop" style="display:none;"></div>
          </div>
        </label>
        <label>标题（可选）<input class="inp" id="compose-title" placeholder="一句话标题"></label>
        <label>想说些什么？<textarea class="inp inp-ta" id="compose-content" rows="5" placeholder="写下你想说的话……"></textarea></label>
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
          <button class="btn btn-pri" onclick="_doSendMail()" id="compose-btn">寄出这封信</button>
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
        drop.innerHTML = '<div class="mailbox-search-item" style="color:var(--ink-faint);">没有找到这个用户</div>';
        drop.style.display = 'block';
        return;
      }
      drop.innerHTML = r.data.users.map(u => `
        <button type="button" class="mailbox-search-item" onclick='_selectRecipient(${App._js(u.username)})'>
          <span class="mailbox-search-avatar">${u.username[0]}</span> ${App._e(u.username)}
        </button>
      `).join('');
      drop.style.display = 'block';
    } catch (e) { /* silent */ }
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
  if (!u) { if (status) status.textContent = '写上收件人的名字吧'; return; }
  if (!c) { if (status) status.textContent = '总得写点什么吧'; return; }
  if (btn) btn.disabled = true;
  if (status) status.textContent = '正在寄出……';
  try {
    const postcardId = postcard?.value ? Number(String(postcard.value).replace(/^pc-/, '')) : null;
    const letterId = letter?.value ? Number(String(letter.value).replace(/^ltr-/, '')) : null;
    const r = await api.sendMail(u, title?.value?.trim() || '', c, postcardId, letterId);
    if (r.ok) {
      document.querySelector('.modal')?.remove();
      App.showToast('信已寄出，正在邮路上。');
      _mboxTab = 'outbox';
      const page = document.getElementById('page-mailbox');
      if (page) _renderMailboxCore(page);
    } else {
      if (status) status.textContent = r.error || '没有寄出去';
    }
  } catch (e) { if (status) status.textContent = '网络不好，再试一次'; }
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
