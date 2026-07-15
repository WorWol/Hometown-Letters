/* Full-screen warm pixel workbench UI. Business APIs stay in the original modules. */

const WORKBENCH_PAGE_META = {
  game: ['DESKTOP · 暖灯已亮', '桌上的来信', '把今天轻轻放下，也听一听过去的回声。'],
  write_letter: ['WRITE · 寄往过去', '写一封信', '把想说的话装进信封，交给时间慢慢送达。'],
  postcards: ['ALBUM · 沿途风景', '明信片墙', '每一张都是过去替你按下的快门。'],
  discover: ['DISCOVER · 远方的风', '发现', '看看其他人写给过去的信，点亮喜欢的，它会落在你的桌上。'],
  mailbox: ['MAILBOX · 故乡邮路', '信箱', '来自其他故乡的信，和寄出去的问候。'],
  memories: ['MEMORY · 旧日手账', '记忆本', '收好那些不起眼，却一直没有离开的片段。'],
  settings: ['SETTINGS · 工作台抽屉', '设置', '整理账户、故乡与这段旅程的状态。'],
};

App.syncShell = function syncShell() {
  const state = this.state || {};
  const day = document.getElementById('shell-day');
  const hometown = document.getElementById('shell-hometown');
  if (day) day.textContent = `第 ${state.currentDay || 0} 天`;
  if (hometown) hometown.textContent = state.hometown?.hometownName || state.hometown?.county || '尚未设置';
};

App.navigate = function navigate(page) {
  const target = document.getElementById(`page-${page}`);
  if (!target) return;
  document.querySelectorAll('#app .page').forEach(node => node.classList.remove('active'));
  target.classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(button => {
    const active = button.dataset.page === page;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const [eyebrow, title, subtitle] = WORKBENCH_PAGE_META[page] || WORKBENCH_PAGE_META.game;
  const eyebrowEl = document.getElementById('workspace-eyebrow');
  const titleEl = document.getElementById('workspace-title');
  const subtitleEl = document.getElementById('workspace-subtitle');
  if (eyebrowEl) eyebrowEl.textContent = eyebrow;
  if (titleEl) titleEl.textContent = title;
  if (subtitleEl) subtitleEl.textContent = subtitle;
  this.currentPage = page;
  this.syncShell();
  const fn = `render${page.split('_').map(part => part[0].toUpperCase() + part.slice(1)).join('')}`;
  if (typeof window[fn] === 'function') window[fn]();
  document.getElementById('workspace-content')?.scrollTo({ top: 0, behavior: 'instant' });
};

App.showPostcardDetail = function showPostcardDetail(pc) {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal workbench-modal';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.onclick = event => { if (event.target === overlay) overlay.remove(); };
  const tags = pc.keywords || pc.tags || [];
  overlay.innerHTML = `
    <div class="modal-pnl postcard-detail-panel">
      <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
      <div class="postcard-detail-visual">
        <div class="postcard-detail-frame" onclick="event.stopPropagation();enlargePostcardImage(this)">${this._imgHtml(pc)}</div>
        <div class="postcard-detail-stamp">故乡<br><small>LETTER</small></div>
      </div>
      <div class="postcard-detail-copy">
        <div class="workspace-eyebrow">POSTCARD · ${this._e(pc.place || '远方')}</div>
        <h3>${this._e(pc.title || '无题明信片')}</h3>
        <div class="modal-meta">${this._e(pc.place || '')}${pc.place && pc.mood ? ' · ' : ''}${this._e(pc.mood || '')}${pc.createdAt ? ` · ${new Date(pc.createdAt).toLocaleDateString('zh-CN')}` : ''}</div>
        <div class="modal-bd">${this._e(pc.body || '这张明信片没有写下太多，却把那一刻好好留住了。')}</div>
        ${pc.poem ? `<div class="modal-poem">${this._e(pc.poem)}</div>` : ''}
        <div class="modal-tags">${tags.map(tag => `<span class="tag">${this._e(String(tag))}</span>`).join('')}</div>
        ${pc.letterText ? `<div class="letter-echo"><strong>来信回声</strong><p>${this._e(pc.letterText)}</p></div>` : ''}
        <div class="modal-ft"><button class="btn btn-sec" onclick="this.closest('.modal').remove()">收好明信片</button></div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('.modal-cl')?.focus();
};

function renderAuthPage(mode) {
  const el = document.getElementById('page-auth');
  if (!el) return;
  const isLogin = mode === 'login';
  el.innerHTML = `
    <div class="auth-workbench">
      <section class="auth-scene" aria-label="暖灯下的故乡邮箱">
        <div class="auth-scene-copy">
          <span>HOMETOWN LETTERS</span>
          <h1>总有一封信<br>会沿着旧路回来</h1>
          <p>把今天写给过去，也让故乡替你保存那些没有说完的话。</p>
        </div>
      </section>
      <section class="auth-paper">
        <div class="auth-seal">乡</div>
        <div class="auth-heading">
          <div class="workspace-eyebrow">A LETTER TO THE PAST</div>
          <h2>故乡来信</h2>
          <p>${isLogin ? '欢迎回到这张熟悉的书桌。' : '从一封写给过去的信开始。'}</p>
        </div>
        <div class="auth-tabs" role="tablist" aria-label="账户方式">
          <button class="auth-tab ${isLogin ? 'active' : ''}" role="tab" aria-selected="${isLogin}" onclick="renderAuthPage('login')">登录</button>
          <button class="auth-tab ${!isLogin ? 'active' : ''}" role="tab" aria-selected="${!isLogin}" onclick="renderAuthPage('register')">注册</button>
        </div>
        <form class="auth-form" onsubmit="handleAuth(event, '${mode}')">
          <label class="auth-field">你的名字
            <input type="text" id="auth-username" class="inp" placeholder="写下用户名" required minlength="2" maxlength="32" autocomplete="username">
          </label>
          <label class="auth-field">信箱暗号
            <input type="password" id="auth-password" class="inp" placeholder="至少 4 个字符" required minlength="4" autocomplete="${isLogin ? 'current-password' : 'new-password'}">
          </label>
          <div class="auth-err" id="auth-error" role="alert" style="display:none"></div>
          <button type="submit" class="auth-submit" id="auth-submit">${isLogin ? '打开我的信箱' : '寄出第一封信'}</button>
        </form>
        <button class="auth-skip" type="button" onclick="skipAuth()">先看看这间温暖的房间 →</button>
      </section>
    </div>`;
}

function skipAuth() {
  document.getElementById('auth-gate').style.display = 'none';
  document.getElementById('app').style.display = 'grid';
  App.init();
  requestAnimationFrame(() => {
    setTimeout(() => {
      document.querySelector('.room-backdrop')?.classList.add('loaded');
    }, 100);
  });
}

async function showAppAfterAuth() {
  document.getElementById('auth-gate').style.display = 'none';
  document.getElementById('app').style.display = 'grid';
  await App.init();
  requestAnimationFrame(() => {
    setTimeout(() => {
      document.querySelector('.room-backdrop')?.classList.add('loaded');
    }, 100);
  });
}

function showAuthGate() {
  document.getElementById('auth-gate').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
  renderAuthPage('login');
}

function renderGame() {
  const el = document.getElementById('page-game');
  if (!el) return;
  const state = App.state;
  const postcards = state.postcards || [];
  const letters = state.letters || [];
  const memories = state.memories || [];
  const liked = state.likedItems || [];
  const pinned = postcards.slice(0, 4);
  window._workbenchPinnedPostcards = pinned;
  const hasLiked = liked.length > 0;
  const latestEvent = postcards[0] || liked[0] || letters[0] || memories[0];
  window._workbenchLikedPC = {};
  liked.forEach((item, i) => { if (item.postcard) window._workbenchLikedPC[i] = item.postcard; });
  el.innerHTML = `
    <div class="game-grid">
      <section class="cork-panel game-board" aria-labelledby="board-title">
        <div class="panel-heading">
          <div><span class="section-kicker">PINNED MOMENTS</span><h2 id="board-title">钉在板上的近况</h2></div>
          <button class="text-button" onclick="App.navigate('postcards')">打开相册墙 →</button>
        </div>
        ${pinned.length ? `<div class="pinned-grid">${pinned.map((pc, index) => `
          <button class="pinned-card tilt-${index + 1}" onclick="App.showPostcardDetail(window._workbenchPinnedPostcards[${index}])">
            <span class="push-pin" aria-hidden="true"></span>
            <span class="pinned-image">${App._imgHtml(pc)}</span>
            <span class="pinned-copy"><small>${App._e(pc.place || '沿途')}</small><strong>${App._e(pc.title || '无题明信片')}</strong></span>
          </button>`).join('')}</div>` : `
          <div class="visual-empty">
            <img src="assets/workbench/empty-mailbox-card.webp" alt="暖灯、邮箱和空白信纸">
            <div><h3>公告板还在等第一张照片</h3><p>写一封信，时间会带着明信片回来。</p><button class="btn btn-pri" onclick="App.navigate('write_letter')">写第一封信</button></div>
          </div>`}
      </section>
      ${hasLiked ? `<section class="cork-panel game-board liked-board" aria-labelledby="liked-title" style="margin-top:14px;">
        <div class="panel-heading">
          <div><span class="section-kicker">COLLECTED LETTERS</span><h2 id="liked-title">收藏的外来信件</h2></div>
        </div>
        <div class="liked-grid">${liked.map((item, i) => `
          <div class="liked-card">
            <div class="liked-card-header">
              <span class="mailbox-avatar" style="width:24px;height:24px;font-size:11px;">${(item.author?.username || '?')[0]}</span>
              <div><strong>${App._e(item.author?.username || '远方')}</strong><small>${App._e(item.author?.hometown || '')}</small></div>
            </div>
            <p class="liked-text">${App._e((item.text || '').slice(0, 100))}</p>
            <div class="liked-meta">
              ${item.place ? `<span class="tag">📍 ${App._e(item.place)}</span>` : ''}
              ${item.mood ? `<span class="tag">${App._e(item.mood)}</span>` : ''}
            </div>
            ${item.postcard ? `<div class="liked-postcard" onclick="event.stopPropagation();App.showPostcardDetail(window._workbenchLikedPC[${i}])">
              <span class="section-kicker">附明信片</span>
              <strong>${App._e(item.postcard.title || '无题')}</strong>
              <small>${App._e(item.postcard.place || '')}</small>
            </div>` : ''}
          </div>
        `).join('')}</div>
      </section>` : ''}
      <aside class="game-side">
        <section class="paper-panel journey-card">
          <span class="wax-badge">${state.currentDay || 0}</span>
          <span class="section-kicker">TODAY'S JOURNEY</span>
          <h2>第 ${state.currentDay || 0} 天</h2>
          <p>${state.hometown?.hometownName ? `从 ${App._e(state.hometown.hometownName)} 寄来的风，今天也经过了窗边。` : '先在设置里写下故乡，故事就会从那里启程。'}</p>
          <div class="stat-grid">
            <div><strong>${postcards.length}</strong><span>明信片</span></div>
            <div><strong>${letters.length}</strong><span>来往信件</span></div>
            <div><strong>${memories.length}</strong><span>记忆片段</span></div>
          </div>
          <button class="btn btn-big desk-next" onclick="nextDay()" id="g-nextday" ${_gameBusy ? 'disabled' : ''}>${_gameBusy ? '投递中…' : '寄出下一封'}</button>
          <div class="desk-letter-count" aria-live="polite">${postcards.length ? `已经收到 ${postcards.length} 张沿途风景` : '信箱正在等一封新来信'}</div>
        </section>
        <section class="dark-panel event-card">
          <span class="section-kicker">LATEST NOTE</span>
          <h3>工作台上的新动静</h3>
          ${latestEvent ? `<p>${App._e(latestEvent.title || latestEvent.text || latestEvent.body || '又有一段故事被好好收下。')}</p>` : '<p>暂时很安静。窗外的光正慢慢移过桌面。</p>'}
          <button class="text-button light" onclick="App.navigate('memories')">翻开记忆本 →</button>
        </section>
      </aside>
    </div>`;
}

function renderWriteLetter() {
  const el = document.getElementById('page-write_letter');
  if (!el) return;
  const letters = (App.state.letters || []).slice(0, 5);
  el.innerHTML = `
    <div class="write-grid">
      <section class="write-stage paper-panel">
        <div class="writing-desk-label"><span>TO · 过去的自己</span><span>FROM · 今天的我</span></div>
        <div class="env-scene writing" id="env-scene">
          <div class="env-letter-card" id="env-letter-card">
            <textarea class="env-textarea" id="env-textarea" placeholder="写一封给过去自己的信……" rows="9" maxlength="2000"></textarea>
            <div class="env-extra">
              <div class="env-form-row">
                <label class="env-form-group">推荐地点（可选）<input class="env-inp" id="env-place" placeholder="河堤 / 学校后门 / 旧市场"></label>
                <label class="env-form-group">希望的情绪（可选）<input class="env-inp" id="env-mood" placeholder="平静 / 鼓起勇气"></label>
              </div>
            </div>
            <div class="env-step-btns" id="env-step-btns"></div>
            <div class="env-status" id="env-status" aria-live="polite">&nbsp;</div>
          </div>
          <div class="env-envelope-wrap" id="env-envelope-wrap">
            <div class="env-envelope" id="env-envelope" onclick="enlargeEnvelope()">
              <img class="env-stamp" id="env-stamp" src="assets/letters/stamp.png" alt="邮票">
              <div class="env-postmark" id="env-postmark"><span class="env-postmark-inner">故乡<br>2026</span></div>
            </div>
            <div class="env-step-btns" id="env-env-btns"></div>
            <div class="env-status" id="env-env-status" aria-live="polite">&nbsp;</div>
          </div>
        </div>
        <div class="env-mailbox" id="env-mailbox"><img src="assets/letters/env_mailbox.png" alt="邮箱"></div>
      </section>
      <aside class="write-aside">
        <section class="dark-panel delivery-note">
          <span class="section-kicker">DELIVERY GUIDE</span><h3>一封信的旅程</h3>
          <ol><li><span>1</span>写下此刻想说的话</li><li><span>2</span>把信纸装进信封</li><li><span>3</span>贴好属于故乡的邮戳</li><li><span>4</span>投进时间的邮箱</li></ol>
        </section>
        <section class="paper-panel recent-letters">
          <div class="panel-heading compact"><div><span class="section-kicker">RECENT LETTERS</span><h3>最近写过的信</h3></div></div>
          <div class="env-recent" id="env-recent">${letters.length ? letters.map(_renderRecentItem).join('') : '<div class="rl-empty">还没有寄出过信。第一封会很特别。</div>'}</div>
        </section>
        <section class="paper-panel community-panel" id="community-panel"></section>
      </aside>
    </div>`;
  _curStep = LetterStep.WRITING;
  _busy = false;
  _stampApplied = false;
  _generation++;
  _renderButtons();
  setTimeout(() => document.getElementById('env-textarea')?.focus({ preventScroll: true }), 100);
  if (!letters.length) _loadCommunityLetters();
}

/* ── 社区灵感 ── */
async function _loadCommunityLetters() {
  const el = document.getElementById('community-panel');
  if (!el) return;
  el.innerHTML = '<div class="panel-heading compact"><div><span class="section-kicker">INSPIRATION</span><h3>来自其他故乡的来信</h3></div></div><div style="padding:0 16px 16px;"><p style="color:var(--dk-muted);font-size:13px;">正在收集灵感……</p></div>';
  try {
    const r = await api.getCommunityLetters(6);
    if (!r.ok || !r.data || !r.data.letters?.length) { el.innerHTML = ''; return; }
    _renderCommunityCards(el, r.data.letters);
  } catch (e) { el.innerHTML = ''; }
}

function _renderCommunityCards(el, letters) {
  el.innerHTML = `
    <div class="panel-heading compact">
      <div><span class="section-kicker">INSPIRATION</span><h3>来自其他故乡的来信</h3></div>
      <button class="text-button" onclick="_loadCommunityLetters()">↻ 换一批</button>
    </div>
    <div class="community-grid">
      ${letters.map(lt => `
        <button class="community-card" onclick="_fillFromCommunity(${App._js(lt.text)}, ${App._js(lt.place || '')}, ${App._js(lt.mood || '')})">
          <span class="community-text">${App._e(lt.text.length > 80 ? lt.text.slice(0, 80) + '…' : lt.text)}</span>
          <span class="community-meta">
            ${lt.place ? `<span>📍 ${App._e(lt.place)}</span>` : ''}
            ${lt.mood ? `<span>· ${App._e(lt.mood)}</span>` : ''}
            ${lt.hometown?.city ? `<span>· ${App._e(lt.hometown.city)}</span>` : ''}
          </span>
        </button>
      `).join('')}
    </div>`;
}

function _fillFromCommunity(text, place, mood) {
  const ta = document.getElementById('env-textarea');
  const pi = document.getElementById('env-place');
  const mi = document.getElementById('env-mood');
  if (ta) { ta.value = text; ta.focus(); }
  if (pi && place) pi.value = place;
  if (mi && mood) mi.value = mood;
  App.showToast('已填入灵感，改一改再装信封吧', 2000);
  document.getElementById('env-letter-card')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
}

/* ── 信箱页面 ── */
function renderMailbox() {
  const el = document.getElementById('page-mailbox');
  if (!el) return;
  if (typeof _renderMailboxCore === 'function') {
    _renderMailboxCore(el);
  } else {
    el.innerHTML = '<div class="visual-empty"><div><h3>信箱模块加载中</h3><p>请稍候。</p></div></div>';
  }
}

let _workbenchPostcardQuery = '';
function filterPostcards(value) {
  _workbenchPostcardQuery = value;
  renderPostcards();
  const input = document.getElementById('pc-filter');
  if (input) { input.focus(); input.setSelectionRange(input.value.length, input.value.length); }
}

function renderPostcards() {
  const el = document.getElementById('page-postcards');
  if (!el) return;
  const all = App.state.postcards || [];
  const query = _workbenchPostcardQuery.trim().toLowerCase();
  const filtered = query ? all.filter(pc => `${pc.place || ''} ${pc.mood || ''} ${(pc.tags || pc.keywords || []).join(' ')} ${pc.title || ''} ${pc.body || ''}`.toLowerCase().includes(query)) : all;
  window._workbenchFilteredPostcards = filtered;
  el.innerHTML = `
    <section class="album-toolbar paper-panel">
      <div><span class="section-kicker">COLLECTION</span><strong>${filtered.length}</strong><span> / ${all.length} 张明信片</span></div>
      <label class="search-box"><span>⌕</span><input class="inp" id="pc-filter" value="${App._e(_workbenchPostcardQuery)}" placeholder="搜索地点、情绪或标题" oninput="filterPostcards(this.value)"></label>
    </section>
    ${filtered.length ? `<div class="postcard-wall">${filtered.map((pc, index) => `
      <button class="album-card" onclick="App.showPostcardDetail(window._workbenchFilteredPostcards[${index}])">
        <span class="album-photo">${App._imgHtml(pc)}</span>
        <span class="album-copy"><small>${App._e(pc.place || '沿途')} ${pc.createdAt ? `· ${new Date(pc.createdAt).toLocaleDateString('zh-CN')}` : ''}</small><strong>${App._e(pc.title || '无题明信片')}</strong><em>${App._e(pc.mood || '一段安静的时光')}</em></span>
      </button>`).join('')}</div>` : `
      <div class="visual-empty wide-empty"><img src="assets/workbench/empty-mailbox-card.webp" alt="空白信纸与暖灯"><div><h3>${query ? '没有找到这段风景' : '相册墙还是空的'}</h3><p>${query ? '换一个地点或情绪试试。' : '寄出一封信，第一张明信片就会被钉在这里。'}</p>${query ? '<button class="btn btn-sec" onclick="filterPostcards(\'\')">清除搜索</button>' : '<button class="btn btn-pri" onclick="App.navigate(\'write_letter\')">去写信</button>'}</div></div>`}`;
}

function renderMemories() {
  const el = document.getElementById('page-memories');
  if (!el) return;
  const memories = App.state.memories || [];
  const profile = App.state.pastSelfProfile || {};
  const places = profile.latent_place_affinities || [];
  const sensory = profile.sensory_biases || [];
  const identity = profile.identity_signals || [];
  window._workbenchMemories = memories;
  el.innerHTML = `
    <div class="memory-grid">
      <section class="memory-list-panel paper-panel">
        <div class="panel-heading"><div><span class="section-kicker">${memories.length} NOTES</span><h2>被时间收好的片段</h2></div><button class="btn btn-pri" onclick="showMemForm()">记下一件小事</button></div>
        ${memories.length ? `<div class="memory-list">${memories.map((memory, index) => `
          <button class="memory-note" onclick="showMemDetail(window._workbenchMemories[${index}])">
            <span class="memory-date">${memory.timestamp ? new Date(memory.timestamp).toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' }) : '旧日'}</span>
            <span class="memory-body"><strong>${App._e((memory.text || '').slice(0, 80))}</strong><small>${memory.tags?.length ? memory.tags.map(tag => `#${App._e(tag)}`).join('  ') : '一段没有贴标签的回忆'}</small></span>
            <span class="memory-arrow">→</span>
          </button>`).join('')}</div>` : `<div class="visual-empty memory-empty"><img src="assets/workbench/empty-mailbox-card.webp" alt="空白手账与暖灯"><div><h3>第一页还没有落笔</h3><p>记下一个气味、一阵风，或者某个突然想起的人。</p><button class="btn btn-pri" onclick="showMemForm()">写下第一条记忆</button></div></div>`}
      </section>
      <aside class="portrait-card dark-panel">
        <div class="portrait-window"><span>我</span></div>
        <span class="section-kicker">PAST SELF PORTRAIT</span><h2>过去的我</h2>
        <p>${App._e(profile.summary || '画像还很轻。多写下一些记忆，它会逐渐看清过去的你。')}</p>
        ${places.length ? `<div class="profile-section"><strong>总会想起的地方</strong><div class="chip-row">${places.slice(0, 6).map(item => `<span>${App._e(item.name || '')}</span>`).join('')}</div></div>` : ''}
        ${sensory.length ? `<div class="profile-section"><strong>风、光和气味</strong><div class="chip-row sage">${sensory.slice(0, 6).map(item => `<span>${App._e(item.name || '')}</span>`).join('')}</div></div>` : ''}
        ${identity.length ? `<div class="profile-section"><strong>过去留下的线索</strong>${identity.slice(0, 4).map(item => `<small>· ${App._e(item.name || '')}</small>`).join('')}</div>` : ''}
      </aside>
    </div>`;
}

function showMemDetail(memory) {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.onclick = event => { if (event.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <div class="modal-pnl memory-dialog paper-panel">
      <div class="modal-hd"><div><span class="section-kicker">MEMORY NOTE</span><h3>这段记忆</h3></div><button class="modal-cl" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button></div>
      <div class="modal-meta">${memory.timestamp ? new Date(memory.timestamp).toLocaleString('zh-CN') : '旧日片段'}${memory.analysisStatus ? ` · ${_as(memory.analysisStatus)}` : ''}</div>
      <div class="modal-bd">${App._e(memory.text || '')}</div>
      ${memory.summary ? `<div class="modal-poem">${App._e(memory.summary)}</div>` : ''}
      ${memory.tags?.length ? `<div class="modal-tags">${memory.tags.map(tag => `<span class="tag">#${App._e(tag)}</span>`).join('')}</div>` : ''}
      <div class="modal-ft"><button class="btn btn-sec" onclick="this.closest('.modal').remove()">合上这一页</button></div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('.modal-cl')?.focus();
}

function showMemForm() {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.onclick = event => { if (event.target === overlay) overlay.remove(); };
  overlay.innerHTML = `
    <div class="modal-pnl memory-dialog paper-panel">
      <div class="modal-hd"><div><span class="section-kicker">NEW MEMORY</span><h3>记下一件小事</h3></div><button class="modal-cl" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button></div>
      <div class="memory-form">
        <label>此刻想起了什么？<textarea class="inp inp-ta" id="mem-text" rows="6" placeholder="某个地方、某种气味、某一个瞬间……"></textarea></label>
        <div class="memory-form-row">
          <label>标签（逗号分隔）<input class="inp" id="mem-tags" placeholder="家、学校、夏天"></label>
          <label>地点（可选）<input class="inp" id="mem-place" placeholder="例如：秀流公园"></label>
        </div>
        <div class="setting-actions"><button class="btn btn-pri" onclick="saveMem()" id="mem-btn">保存这段记忆</button><span class="st" id="mem-status" aria-live="polite">&nbsp;</span></div>
      </div>
    </div>`;
  document.body.appendChild(overlay);
  overlay.querySelector('#mem-text')?.focus();
}

function renderSettings() {
  const el = document.getElementById('page-settings');
  if (!el) return;
  const state = App.state;
  const user = Auth.getUser();
  el.innerHTML = `
    <div class="settings-grid">
      <section class="drawer-card paper-panel">
        <div class="drawer-handle"></div><span class="section-kicker">ACCOUNT</span><h2>账户抽屉</h2>
        <div class="setting-line"><span>现在使用的名字</span><strong>${App._e(user?.username || '访客')}</strong></div>
        <p>退出后，本地保存的登录凭据会被清除。</p>
        ${user ? '<button class="btn btn-dng" onclick="doLogout()">退出登录</button>' : '<button class="btn btn-sec" onclick="showAuthGate()">前往登录</button>'}
      </section>
      <section class="drawer-card paper-panel hometown-drawer">
        <div class="drawer-handle"></div><span class="section-kicker">HOMETOWN</span><h2>故乡地址</h2>
        <div class="settings-form-grid">
          <label>省份<input class="inp" id="s-prov" value="${App._e(state.hometown?.province || '湖南')}"></label>
          <label>城市<input class="inp" id="s-city" value="${App._e(state.hometown?.city || '郴州')}"></label>
          <label>区 / 县<input class="inp" id="s-county" value="${App._e(state.hometown?.county || '资兴')}"></label>
          <label>故乡称呼<input class="inp" id="s-name" value="${App._e(state.hometown?.hometownName || '资兴')}"></label>
        </div>
        <div class="setting-actions"><button class="btn btn-pri" onclick="saveHome()">保存故乡</button><span class="st" id="s-home-st" aria-live="polite">&nbsp;</span></div>
      </section>
      <section class="drawer-card dark-panel journey-drawer">
        <div class="drawer-handle"></div><span class="section-kicker">JOURNEY STATUS</span><h2>旅程状态</h2>
        <div class="settings-stats"><div><strong>${state.currentDay || 0}</strong><span>天</span></div><div><strong>${(state.postcards || []).length}</strong><span>明信片</span></div><div><strong>${(state.memories || []).length}</strong><span>记忆</span></div><div><strong>${(state.letters || []).length}</strong><span>信件</span></div></div>
      </section>
      <section class="drawer-card paper-panel connection-drawer">
        <div class="drawer-handle"></div><span class="section-kicker">CONNECTION</span><h2>信路连接</h2>
        <label>后端地址<input class="inp" id="s-backend" value="http://127.0.0.1:8787" readonly></label>
        <div class="setting-actions"><button class="btn btn-sec" onclick="checkBack()">检查连接</button><span class="st" id="s-backend-st" aria-live="polite">&nbsp;</span></div>
      </section>
    </div>`;
}

const _workbenchOriginalSaveHome = saveHome;
saveHome = async function saveHomeWorkbench() {
  await _workbenchOriginalSaveHome();
  App.syncShell();
};

const _workbenchOriginalNextDay = nextDay;
nextDay = async function nextDayWorkbench() {
  await _workbenchOriginalNextDay();
  App.syncShell();
};
