/* ================================================================
   故乡来信 · 信箱 (MailboxScene)
   收件箱 / 发件箱 / 寄信
   ================================================================ */

let _mailboxTab = 'inbox';      // 'inbox' | 'outbox'
let _mailboxBusy = false;
let _mailboxUnread = 0;


/* ================ RENDER ================ */

function renderMailbox() {
  const el = document.getElementById('page-mailbox');
  if (!el) return;

  el.innerHTML = `
    <div class="pg-hd">
      <div class="eyebrow">Mailbox</div>
      <h2>信箱</h2>
      <p>来自其他故乡的信，和寄出去的问候。</p>
    </div>

    <div class="mailbox-tabs">
      <button class="mailbox-tab ${_mailboxTab === 'inbox' ? 'active' : ''}"
              onclick="switchMailboxTab('inbox')">
        收件箱${_mailboxUnread > 0 ? `<span class="mailbox-badge">${_mailboxUnread}</span>` : ''}
      </button>
      <button class="mailbox-tab ${_mailboxTab === 'outbox' ? 'active' : ''}"
              onclick="switchMailboxTab('outbox')">
        发件箱
      </button>
      <button class="btn btn-pri mailbox-compose-btn" onclick="showComposeMail()">✉ 写信</button>
    </div>

    <div class="mailbox-list" id="mailbox-list">
      <div class="g-empty"><p>加载中……</p></div>
    </div>
  `;

  _loadMailboxList();
}


/* ================ TAB SWITCH ================ */

function switchMailboxTab(tab) {
  _mailboxTab = tab;
  renderMailbox();
}


/* ================ LOAD ================ */

async function _loadMailboxList() {
  if (_mailboxBusy) return;
  _mailboxBusy = true;

  const listEl = document.getElementById('mailbox-list');
  if (!listEl) { _mailboxBusy = false; return; }

  listEl.innerHTML = '<div class="g-empty"><p>加载中……</p></div>';

  try {
    if (_mailboxTab === 'inbox') {
      const r = await api.getInbox(1, 30);
      if (r.ok && r.data) {
        _mailboxUnread = r.data.unreadCount || 0;
        _renderMailList(listEl, r.data.mails, 'inbox');
        _updateTabBadge();
      } else {
        listEl.innerHTML = '<div class="g-empty"><p>无法加载收件箱</p></div>';
      }
    } else {
      const r = await api.getOutbox(1, 30);
      if (r.ok && r.data) {
        _renderMailList(listEl, r.data.mails, 'outbox');
      } else {
        listEl.innerHTML = '<div class="g-empty"><p>无法加载发件箱</p></div>';
      }
    }
  } catch (e) {
    console.warn('[mailbox] load failed:', e);
    listEl.innerHTML = '<div class="g-empty"><p>加载失败，请检查网络</p></div>';
  }

  _mailboxBusy = false;
}


/* ================ RENDER LIST ================ */

function _renderMailList(container, mails, type) {
  if (!mails || mails.length === 0) {
    container.innerHTML = `
      <div class="g-empty">
        <p>${type === 'inbox' ? '收件箱是空的，还没有人给你寄信。' : '还没有寄出过信。'}</p>
      </div>`;
    return;
  }

  const dateFmt = (ts) => {
    if (!ts) return '';
    const d = new Date(ts);
    const now = new Date();
    const diff = now - d;
    if (diff < 86400000) return d.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
    return d.toLocaleDateString('zh-CN');
  };

  container.innerHTML = mails.map(m => `
    <div class="mailbox-item ${!m.isRead && type === 'inbox' ? 'unread' : ''}"
         onclick="showMailDetail('${m.id}', '${type}')">
      <div class="mailbox-item-left">
        <div class="mailbox-item-avatar">
          ${(type === 'inbox' ? (m.senderUsername || '?') : (m.recipientUsername || '?'))[0]}
        </div>
      </div>
      <div class="mailbox-item-body">
        <div class="mailbox-item-top">
          <span class="mailbox-item-user">
            ${type === 'inbox' ? App._e(m.senderUsername || '未知用户') : '发给 ' + App._e(m.recipientUsername || '未知用户')}
          </span>
          <span class="mailbox-item-time">${dateFmt(m.sentAt)}</span>
        </div>
        <div class="mailbox-item-title">${App._e(m.title || '(无标题)')}</div>
        <div class="mailbox-item-preview">${App._e((m.content || '').slice(0, 80))}</div>
        ${m.attachedPostcard ? '<span class="mailbox-item-attach">📮 附明信片</span>' : ''}
        ${m.attachedLetter ? '<span class="mailbox-item-attach">✉ 附来信</span>' : ''}
      </div>
      ${!m.isRead && type === 'inbox' ? '<div class="mailbox-item-dot"></div>' : ''}
    </div>
  `).join('');
}


/* ================ UPDATE BADGE ================ */

function _updateTabBadge() {
  const tabBtns = document.querySelectorAll('.mailbox-tab');
  if (tabBtns.length > 0) {
    const inboxBtn = tabBtns[0];
    const existingBadge = inboxBtn.querySelector('.mailbox-badge');
    if (_mailboxUnread > 0) {
      if (existingBadge) {
        existingBadge.textContent = _mailboxUnread;
      } else {
        inboxBtn.innerHTML += `<span class="mailbox-badge">${_mailboxUnread}</span>`;
      }
    } else if (existingBadge) {
      existingBadge.remove();
    }
  }
}


/* ================ MAIL DETAIL MODAL ================ */

async function showMailDetail(mailId, type) {
  const modal = document.querySelector('.modal');
  if (modal) modal.remove();

  // Show loading
  const overlay = document.createElement('div');
  overlay.className = 'modal';
  overlay.innerHTML = '<div class="modal-pnl"><div class="modal-bd" style="text-align:center;padding:40px;">加载中……</div></div>';
  document.body.appendChild(overlay);

  try {
    // Mark as read if inbox
    if (type === 'inbox') {
      await api.markMailRead(mailId).catch(() => {});
      _mailboxUnread = Math.max(0, _mailboxUnread - 1);
    }

    const r = await api.getMailDetail(mailId);
    if (!r.ok || !r.data) {
      overlay.innerHTML = '<div class="modal-pnl"><div class="modal-bd" style="text-align:center;padding:40px;">无法加载信件</div></div>';
      return;
    }
    const m = r.data;

    const dateFmt = (ts) => {
      if (!ts) return '';
      return new Date(ts).toLocaleString('zh-CN');
    };

    let attachmentHtml = '';
    if (m.attachedPostcard) {
      const pc = m.attachedPostcard;
      const imgHtml = pc.imageUrl
        ? `<img src="${App._e(pc.imageUrl)}" alt="" style="max-width:100%;border-radius:6px;margin-top:8px;" onerror="this.style.display='none'">`
        : '';
      attachmentHtml = `
        <div class="mailbox-attach-card">
          <div class="mailbox-attach-label">📮 附带的明信片</div>
          <div style="font-weight:600;margin:4px 0;">${App._e(pc.title || '无题')}</div>
          <div style="color:var(--dk-muted);font-size:13px;">${App._e(pc.place || '')} · ${App._e(pc.mood || '')}</div>
          ${imgHtml}
        </div>`;
    }
    if (m.attachedLetter) {
      const lt = m.attachedLetter;
      attachmentHtml += `
        <div class="mailbox-attach-card">
          <div class="mailbox-attach-label">✉ 附带的来信</div>
          <div style="color:var(--dk-muted);font-size:13px;margin-top:4px;">${App._e((lt.text || '').slice(0, 200))}</div>
        </div>`;
    }

    overlay.innerHTML = `
      <div class="modal-pnl" style="max-width:520px;">
        <div class="modal-hd">
          <h3>${App._e(m.title || '(无标题)')}</h3>
          <button class="modal-cl" onclick="this.closest('.modal').remove()">×</button>
        </div>
        <div class="modal-meta">
          ${type === 'inbox' ? '来自 ' + App._e(m.senderUsername) : '发给 ' + App._e(m.recipientUsername)}
          · ${dateFmt(m.sentAt)}
        </div>
        <div class="modal-bd" style="white-space:pre-wrap;">${App._e(m.content || '')}</div>
        ${attachmentHtml}
        <div class="modal-ft" style="display:flex;justify-content:space-between;align-items:center;">
          <button class="btn btn-dng" onclick="deleteMailConfirm('${m.id}')">删除</button>
          <button class="btn btn-sec" onclick="this.closest('.modal').remove()">关闭</button>
        </div>
      </div>`;

    _updateTabBadge();

  } catch (e) {
    console.warn('[mailbox] detail load failed:', e);
    overlay.innerHTML = '<div class="modal-pnl"><div class="modal-bd" style="text-align:center;padding:40px;">加载失败</div></div>';
  }
}


/* ================ DELETE ================ */

async function deleteMailConfirm(mailId) {
  const modal = document.querySelector('.modal');
  if (!modal) return;

  modal.innerHTML = `
    <div class="modal-pnl" style="max-width:360px;">
      <div class="modal-hd"><h3>删除信件</h3></div>
      <div class="modal-bd" style="text-align:center;padding:20px;">
        <p style="color:var(--dk-muted);">确定要删除这封信吗？</p>
      </div>
      <div class="modal-ft" style="display:flex;gap:8px;justify-content:center;">
        <button class="btn btn-dng" onclick="doDeleteMail('${mailId}')">删除</button>
        <button class="btn btn-sec" onclick="this.closest('.modal').remove()">取消</button>
      </div>
    </div>`;
}

async function doDeleteMail(mailId) {
  try {
    const r = await api.deleteMail(mailId);
    document.querySelector('.modal')?.remove();
    if (r.ok) {
      App.showToast('信件已删除');
      _loadMailboxList();
    } else {
      App.showToast('删除失败: ' + (r.error || '未知错误'), 3000);
    }
  } catch (e) {
    App.showToast('网络错误', 3000);
    console.error(e);
  }
}


/* ================ COMPOSE ================ */

function showComposeMail() {
  const modal = document.querySelector('.modal');
  if (modal) modal.remove();

  const overlay = document.createElement('div');
  overlay.className = 'modal';
  overlay.innerHTML = `
    <div class="modal-pnl" style="max-width:500px;">
      <div class="modal-hd">
        <h3>✉ 写一封信</h3>
        <button class="modal-cl" onclick="this.closest('.modal').remove()">×</button>
      </div>
      <div style="padding:14px 24px 20px;">
        <div class="fg" style="margin-bottom:12px;">
          <label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--dk-sec);">收件人</label>
          <div style="position:relative;">
            <input class="inp" id="compose-recipient" placeholder="输入用户名搜索……" autocomplete="off"
                   oninput="searchRecipient(this.value)">
            <div class="mailbox-search-drop" id="compose-search-drop" style="display:none;"></div>
          </div>
        </div>
        <div class="fg" style="margin-bottom:12px;">
          <label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--dk-sec);">标题</label>
          <input class="inp" id="compose-title" placeholder="一句话标题">
        </div>
        <div class="fg" style="margin-bottom:12px;">
          <label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--dk-sec);">内容</label>
          <textarea class="inp inp-ta" id="compose-content" rows="5" placeholder="写下你想说的话……"></textarea>
        </div>
        <button class="btn btn-pri" onclick="doSendMail()" id="compose-btn" style="margin-top:8px;">寄出</button>
        <div class="st" id="compose-status">&nbsp;</div>
      </div>
    </div>`;

  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);
}

let _searchTimer = null;

async function searchRecipient(query) {
  clearTimeout(_searchTimer);
  const drop = document.getElementById('compose-search-drop');
  if (!drop) return;

  if (!query || query.trim().length < 1) {
    drop.style.display = 'none';
    return;
  }

  _searchTimer = setTimeout(async () => {
    try {
      const r = await api.lookupUsers(query.trim());
      if (!r.ok || !r.data || !r.data.users || r.data.users.length === 0) {
        drop.innerHTML = '<div class="mailbox-search-item" style="color:var(--dk-muted);">未找到用户</div>';
        drop.style.display = 'block';
        return;
      }
      drop.innerHTML = r.data.users.map(u => `
        <div class="mailbox-search-item" onclick="selectRecipient('${App._e(u.username)}')">
          <span class="mailbox-search-avatar">${u.username[0]}</span>
          ${App._e(u.username)}
        </div>
      `).join('');
      drop.style.display = 'block';
    } catch (e) {
      console.warn('[compose] search failed:', e);
    }
  }, 300);
}

function selectRecipient(username) {
  const inp = document.getElementById('compose-recipient');
  const drop = document.getElementById('compose-search-drop');
  if (inp) inp.value = username;
  if (drop) drop.style.display = 'none';
}

async function doSendMail() {
  const recipient = document.getElementById('compose-recipient');
  const title = document.getElementById('compose-title');
  const content = document.getElementById('compose-content');
  const btn = document.getElementById('compose-btn');
  const status = document.getElementById('compose-status');

  const recipientVal = recipient ? recipient.value.trim() : '';
  const contentVal = content ? content.value.trim() : '';

  if (!recipientVal) { if (status) status.textContent = '请输入收件人用户名'; return; }
  if (!contentVal) { if (status) status.textContent = '请写下一些话'; return; }

  if (btn) btn.disabled = true;
  if (status) status.textContent = '寄出中……';

  try {
    const r = await api.sendMail(
      recipientVal,
      title ? title.value.trim() : '',
      contentVal
    );
    if (r.ok) {
      document.querySelector('.modal')?.remove();
      App.showToast('信件已寄出');
      switchMailboxTab('outbox');
    } else {
      if (status) status.textContent = r.error || '寄出失败';
    }
  } catch (e) {
    if (status) status.textContent = '网络错误';
    console.error(e);
  }

  if (btn) btn.disabled = false;
}


/* ================ NAV UPDATE ================ */

// Close search dropdown on outside click
document.addEventListener('click', function(e) {
  const drop = document.getElementById('compose-search-drop');
  if (drop && !e.target.closest('#compose-recipient') && !e.target.closest('#compose-search-drop')) {
    drop.style.display = 'none';
  }
});
