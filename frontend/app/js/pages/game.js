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
          <div><span class="section-kicker">PINNED MOMENTS</span><h2>钉在回忆板上的明信片</h2></div>
          <button class="text-button" onclick="App.navigate('postcards')">打开相册墙 →</button>
        </div>
        ${pinned.length ? `<div class="pinned-grid">${pinned.map((pc, index) => `
          <button class="pinned-card tilt-${index + 1}" onclick="App.showPostcardDetail(window._gamePinned[${index}])">
            <span class="push-pin" aria-hidden="true"></span>
            <span class="pinned-image">${App._backgroundMediaHtml(pc, { small: true })}</span>
            <span class="pinned-copy"><small>${App._e(pc.place || '沿途')}</small><strong>${App._e(pc.title || '无题明信片')}</strong></span>
          </button>`).join('')}</div>` : `
          <div class="visual-empty large-empty">
            <img src="assets/workbench/empty-mailbox-card.webp" alt="暖灯、邮箱和空白信纸">
            <div><h3>公告板还在等第一张照片</h3><p>写一封信，时间会带着明信片回来。</p><button class="btn btn-pri" onclick="App.navigate('write_letter')">写第一封信</button></div>
          </div>`}
      </section>
      <aside class="game-side">
        <section class="paper-panel journey-card">
          <span class="wax-badge">${state.currentDay || 0}</span>
          <span class="section-kicker">TODAY'S JOURNEY</span>
          <h2>第 ${state.currentDay || 0} 天</h2>
          <p>${state.hometown?.hometownName ? `从 ${App._e(state.hometown.hometownName)} 寄来的风，今天也经过了窗边。` : '先在设置里写下故乡，邮路才知道从哪里出发。'}</p>
          <div class="stat-grid three"><div><strong>${postcards.length}</strong><span>明信片</span></div><div><strong>${letters.length}</strong><span>信件</span></div><div><strong>${memories.length}</strong><span>记忆</span></div></div>
          <button class="btn btn-pri btn-wide" onclick="nextDay()" id="g-nextday" ${_gameBusy ? 'disabled' : ''}>${_gameBusy ? '投递中…' : '寄出下一封'}</button>
          <p class="status-line" id="game-status" aria-live="polite">&nbsp;</p>
        </section>
        <section class="dark-panel latest-card">
          <span class="section-kicker">LATEST NOTE</span>
          <h3>书桌上的最新动静</h3>
          ${latest ? `<p>${App._e((latest.title || latest.text || latest.body || '一段新的回声').slice(0, 100))}</p><small>${App._e(latest.place || latest.mood || '刚刚')}</small>` : '<p>灯亮着，桌面安安静静。第一封信会让这里有故事。</p>'}
        </section>
      </aside>
    </div>`;
}

async function nextDay() {
  if (_gameBusy) return;
  _gameBusy = true;
  const button = document.getElementById('g-nextday');
  const status = document.getElementById('game-status');
  if (button) { button.disabled = true; button.textContent = '投递中…'; }
  if (status) status.textContent = '正在沿着故乡邮路寄出…';
  try {
    if (!App.state.initialized) {
      const init = await api.initHometown({ province: '湖南', city: '郴州', county: '资兴', hometown_name: '资兴' });
      if (init.ok) App.applyState({ ...App.state, initialized: true, hometown: init.data.hometown, profile: init.data.profile });
    }
    const response = await api.sendLetter('今天天气不错，我想去走走看看。', App.state.hometown?.hometownName || '资兴', '平静');
    if (!response.ok) throw new Error(response.error || '未能寄出');
    await App.refreshState();
    App.showToast('新的明信片已到达');
    if (response.data) setTimeout(() => App.showPostcardDetail(App.normalizePostcard(response.data)), 360);
  } catch (error) {
    if (status) status.textContent = error.message || '网络错误';
  } finally {
    _gameBusy = false;
    renderGame();
  }
}
