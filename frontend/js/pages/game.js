/* ===== 桌面场景 — 木质书桌上的明信片 ===== */

let _gameBusy = false;

function deskCardTransform(index) {
  const rotate = [-4, 3, -2, 5, -3, 2, -5, 4][index % 8];
  const shiftY = [0, 10, -6, 12, -10, 8, -4, 6][index % 8];
  return `transform: rotate(${rotate}deg) translateY(${shiftY}px);`;
}

function renderGame() {
  const el = document.getElementById('page-game');
  if (!el) return;
  const state = App.state;
  const pcs = state.postcards || [];
  const has = pcs.length > 0;
  const latest = pcs[0] || null;

  /* ── 桌面物件 HTML ── */
  const deskItems = `
    <!-- 台灯 -->
    <div class="desk-lamp">
      <div class="lamp-shade"></div>
      <div class="lamp-arm"></div>
      <div class="lamp-base"></div>
    </div>
    <!-- 灯光辉晕 -->
    <div class="desk-light"></div>
    <!-- 茶杯 -->
    <div class="desk-teacup">
      <div class="teacup-body"></div>
      <div class="teacup-handle"></div>
      <div class="teacup-steam"></div>
    </div>
    <!-- 钢笔 + 墨水瓶 -->
    <div class="desk-inkwell">
      <div class="inkwell-body"></div>
      <div class="inkwell-cap"></div>
    </div>
    <div class="desk-pen">
      <div class="pen-body"></div>
      <div class="pen-nib"></div>
      <div class="pen-clip"></div>
    </div>`;

  let cards = '';
  if (has) {
    cards = pcs.map((pc, i) => {
      return `<button class="pc-card"
                style="${deskCardTransform(i)}"
                onclick="App.showPostcardDetail(pc__${i})">
          <div class="pc-card-sh"></div>
          <div class="pc-card-bd">
            <div class="pc-fr">${App._imgHtml(pc)}</div>
            <div class="pc-body">
              <div class="loc">${App._e(pc.place||'')}</div>
              <div class="tit">${App._e(pc.title||'无题')}</div>
            </div>
          </div>
        </button>`;
    }).join('');
    window._tdPCs = pcs;
    cards = cards.replace(/pc__(\d+)/g, (_, i) => `window._tdPCs[${i}]`);
  }

  el.innerHTML = `
    <div class="desk-surface">
      ${deskItems}
      <div class="desk-grain"></div>
    </div>
    <div class="desk-overview">
      <div class="desk-copy">
        <div class="desk-kicker">Desktop</div>
        <h2>桌上的来信</h2>
        <p>${has ? '这些明信片会直接铺在桌面上，方便你先看画面，再决定要不要展开细读。' : '桌面已经准备好了。先写一封信，第一张明信片就会落在这里。'}</p>
        <div class="desk-stats">
          <span class="desk-stat">第 ${state.currentDay||0} 天</span>
          <span class="desk-stat">${pcs.length} 张明信片</span>
          <span class="desk-stat">${(state.letters||[]).length} 封来信</span>
        </div>
      </div>
      ${latest ? `
        <div class="desk-feature" onclick="App.showPostcardDetail(window._tdPCs[0])">
          <div class="desk-feature-label">最新收到</div>
          <div class="desk-feature-frame">${App._imgHtml(latest)}</div>
          <div class="desk-feature-meta">
            <div class="desk-feature-place">${App._e(latest.place || '未知地点')}</div>
            <div class="desk-feature-title">${App._e(latest.title || '无题明信片')}</div>
          </div>
        </div>` : ''}
    </div>
    ${has ? `<div class="pc-stack">${cards}</div>` : `
      <div class="pc-stack">
        <div class="stack-empty">
          <div class="empty-lamp-glow"></div>
          <h3>桌面还很干净</h3>
          <p>灯亮着，纸笔备好了。写第一封信吧。</p>
          <button class="btn btn-pri" onclick="App.navigate('write_letter')">写第一封信</button>
        </div>
      </div>`}
    <div class="desk-foot">
      <span class="desk-day">第 ${state.currentDay||0} 天</span>
      <span class="desk-letter-count">${has ? `${pcs.length} 封来信` : ''}</span>
      <button class="btn btn-big desk-next" onclick="nextDay()" id="g-nextday" ${_gameBusy?'disabled':''}>${_gameBusy?'投递中…':'寄出下一封'}</button>
    </div>`;
}

async function nextDay() {
  if (_gameBusy) return;
  _gameBusy = true;
  const btn = document.getElementById('g-nextday');
  const st = document.querySelector('.desk-letter-count');
  if (btn) { btn.disabled = true; btn.textContent = '投递中…'; }
  if (st) st.textContent = '正在寄出…';

  try {
    if (!App.state.initialized) {
      const r = await api.initHometown({ user_id:'default', province:'湖南', city:'郴州', county:'资兴', hometown_name:'资兴' });
      if (r.ok) { App.state.initialized = true; App.state.hometown = r.data.hometown; App.state.profile = r.data.profile; }
    }
    const lr = await api.sendLetter('今天天气不错，我想去走走看看。', App.state.hometown?.hometownName||'资兴', '平静');
    if (lr.ok) {
      const sr = await api.getState();
      if (sr.ok) { App.state.postcards = sr.data.postcards||[]; App.state.currentDay = sr.data.current_day||0; }
      if (st) st.textContent = `${App.state.postcards.length||0} 封来信`;
      App.showToast('新的明信片已到达');
      if (lr.data) setTimeout(() => App.showPostcardDetail(lr.data), 500);
    } else {
      if (st) st.textContent = lr.error||'未能寄出';
    }
  } catch(e) {
    if (st) st.textContent = '网络错误';
    console.error(e);
  }
  _gameBusy = false;
  if (btn) { btn.disabled = false; btn.textContent = '寄出下一封'; }
  renderGame();
}
