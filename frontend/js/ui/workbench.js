/* 全屏工作台壳层、导航和通用弹窗。页面渲染器位于 pages/。 */

const WORKBENCH_PAGE_META = {
  game: ['DESKTOP · 暖灯已亮', '桌上的来信', '把今天轻轻放下，也听一听过去的回声。'],
  write_letter: ['WRITE · 寄往过去', '写一封信', '把想说的话装进信封，交给时间慢慢送达。'],
  postcards: ['ALBUM · 沿途风景', '明信片墙', '每一张，都是过去替你按下的快门。'],
  discover: ['DISCOVER · 远方的风', '发现', '看看其他人的来信，收藏一段与你相似的回望。'],
  mailbox: ['MAILBOX · 故乡邮路', '信箱', '收好远方寄来的问候，也把自己的心意送出去。'],
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
  if (this.currentPage === 'write_letter' && page !== 'write_letter' && typeof window.saveLetterDraft === 'function') {
    window.saveLetterDraft({ silent: true });
  }
  document.querySelectorAll('#app .page').forEach(node => node.classList.remove('active'));
  target.classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(button => {
    const active = button.dataset.page === page;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const [eyebrow, title, subtitle] = WORKBENCH_PAGE_META[page] || WORKBENCH_PAGE_META.game;
  document.getElementById('workspace-eyebrow').textContent = eyebrow;
  document.getElementById('workspace-title').textContent = title;
  document.getElementById('workspace-subtitle').textContent = subtitle;
  this.currentPage = page;
  this.syncShell();
  const fn = `render${page.split('_').map(part => part[0].toUpperCase() + part.slice(1)).join('')}`;
  if (typeof window[fn] === 'function') window[fn]();
  const content = document.getElementById('workspace-content');
  if (content) content.scrollTop = 0;
};

App.createModal = function createModal(content, className = '') {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = `modal workbench-modal ${className}`.trim();
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.addEventListener('click', event => { if (event.target === overlay) overlay.remove(); });
  overlay.innerHTML = content;
  document.body.appendChild(overlay);
  overlay.querySelector('.modal-cl, button, input, textarea')?.focus();
  return overlay;
};

App.showPostcardDetail = function showPostcardDetail(rawPostcard) {
  const pc = this.normalizePostcard(rawPostcard);
  if (!pc) return;
  const tags = pc.keywords || pc.tags || [];
  this.createModal(`
    <div class="modal-pnl postcard-detail-panel">
      <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
      <div class="postcard-detail-visual">
        <button class="postcard-detail-frame" aria-label="放大明信片画面" onclick="event.stopPropagation();enlargePostcardImage(this)">${this._imgHtml(pc)}</button>
        <span class="postcard-detail-stamp">故乡<small>LETTER</small></span>
      </div>
      <div class="postcard-detail-copy">
        <span class="section-kicker">POSTCARD · ${this._e(pc.place || '远方')}</span>
        <h3>${this._e(pc.title || '无题明信片')}</h3>
        <div class="modal-meta">${this._e(pc.place || '')}${pc.place && pc.mood ? ' · ' : ''}${this._e(pc.mood || '')}${pc.createdAt ? ` · ${new Date(pc.createdAt).toLocaleDateString('zh-CN')}` : ''}</div>
        ${pc.generationPlace ? `<div class="modal-source-place">画面取景：${this._e(pc.generationPlace)}</div>` : ''}
        <div class="modal-bd">${this._e(pc.body || '这张明信片没有写下太多，却把那一刻好好留住了。')}</div>
        ${pc.poem ? `<div class="modal-poem">${this._e(pc.poem)}</div>` : ''}
        <div class="modal-tags">${tags.map(tag => `<span class="tag">${this._e(String(tag))}</span>`).join('')}</div>
        ${pc.letterText ? `<div class="letter-echo"><strong>来信回声</strong><p>${this._e(pc.letterText)}</p></div>` : ''}
        <div class="modal-ft"><button class="btn btn-sec" onclick="this.closest('.modal').remove()">收好明信片</button></div>
      </div>
    </div>`, 'postcard-modal');
};
