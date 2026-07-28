/* 桌面首页。 */

let _gameBusy = false;

function renderGame() {
  const el = document.getElementById('page-game');
  if (!el) return;
  const state = App.state;
  const postcards = state.postcards || [];
  const letters = state.letters || [];
  const memories = state.memories || [];
  const pinned = postcards.slice(0, 4);
  const latest = postcards[0] || letters[0] || memories[0];
  window._gamePinned = pinned;
  el.innerHTML = `
    <div class="game-grid">
      <section class="cork-panel game-board">
        <div class="panel-heading">
          <div><span class="section-kicker">PINNED POSTCARDS</span><h2>钉在回忆板上的明信片</h2></div>
          <button class="text-button" onclick="App.navigate('postcards')">查看全部 →</button>
        </div>
        ${pinned.length ? `<div class="pinned-grid">${pinned.map((pc, index) => `
          <button class="pinned-card tilt-${index + 1}" onclick="App.showPostcardDetail(window._gamePinned[${index}])">
            <span class="push-pin" aria-hidden="true"></span>
            <span class="pinned-image">${App._backgroundMediaHtml(pc, { small: true })}</span>
            <span class="pinned-copy"><small>${App._e(pc.place || '沿途')}</small><strong>${App._e(pc.title || '无题明信片')}</strong></span>
          </button>`).join('')}</div>` : `
          <div class="visual-empty large-empty">
            <img src="assets/workbench/empty-mailbox-card.webp" alt="暖灯、邮箱和空白信纸">
            <div><h3>还没有明信片</h3><p>写完并投递一封信后，这里会显示生成的明信片。</p><button class="btn btn-pri" onclick="App.navigate('write_letter')">写第一封信</button></div>
          </div>`}
      </section>
      <aside class="game-side">
        <section class="paper-panel journey-card">
          <span class="wax-badge">${state.currentDay || 0}</span>
          <span class="section-kicker">TODAY'S JOURNEY</span>
          <h2>第 ${state.currentDay || 0} 天</h2>
          <p>${state.hometown?.hometownName ? `当前故乡：${App._e(state.hometown.hometownName)}` : '请先在设置中填写故乡。'}</p>
          <div class="stat-grid three"><div><strong>${postcards.length}</strong><span>明信片</span></div><div><strong>${letters.length}</strong><span>信件</span></div><div><strong>${memories.length}</strong><span>记忆</span></div></div>
          <button class="btn btn-pri btn-wide" onclick="nextDay()" id="g-nextday" ${_gameBusy ? 'disabled' : ''}>${_gameBusy ? '正在生成…' : '生成今日明信片'}</button>
          <p class="status-line" id="game-status" aria-live="polite">&nbsp;</p>
        </section>
        <section class="dark-panel latest-card">
          <span class="section-kicker">LATEST NOTE</span>
          <h3>最近记录</h3>
          ${latest ? `<p>${App._e((latest.title || latest.text || latest.body || '新的记录').slice(0, 100))}</p><small>${App._e(latest.place || latest.mood || '刚刚')}</small>` : '<p>还没有记录。写下第一封信后，这里会显示最新内容。</p>'}
        </section>
      </aside>
    </div>`;
}

async function nextDay() {
  if (_gameBusy) return;
  _gameBusy = true;
  const button = document.getElementById('g-nextday');
  const status = document.getElementById('game-status');
  if (button) { button.disabled = true; button.textContent = '正在生成…'; }
  if (status) status.textContent = '正在生成今日明信片…';
  try {
    if (!App.state.initialized) {
      const init = await api.initHometown({ province: '湖南', city: '郴州', county: '资兴', hometown_name: '资兴' });
      if (init.ok) App.applyState({ ...App.state, initialized: true, hometown: init.data.hometown, profile: init.data.profile });
    }
    const response = await api.sendLetter('今天天气不错，我想去走走看看。', App.state.hometown?.hometownName || '资兴', '平静');
    if (!response.ok) throw new Error(response.error || '生成失败');
    await App.refreshState();
    App.showToast('今日明信片已生成');
    if (response.data) setTimeout(() => App.showPostcardDetail(App.normalizePostcard(response.data)), 360);
  } catch (error) {
    if (status) status.textContent = App.friendlyError(error, '生成失败，请稍后重试');
  } finally {
    _gameBusy = false;
    renderGame();
  }
}
