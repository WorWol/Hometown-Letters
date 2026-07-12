/* ===== 桌面场景 — 木质书桌上的明信片 ===== */

let _gameBusy = false;

/* 网格散落算法 — 每张卡占一个网格单元，避免堆叠 */
function scatterPositions(count) {
  const pos = [];
  if (count === 0) return pos;

  const cols = Math.min(count, count <= 4 ? 2 : count <= 8 ? 3 : 4);
  const rows = Math.ceil(count / cols);

  /* 桌面可用区域（百分比，避开台灯、茶杯位置） */
  const area = { left: 8, top: 8, right: 78, bottom: 82 };
  const cellW = (area.right - area.left) / cols;
  const cellH = (area.bottom - area.top) / rows;

  for (let i = 0; i < count; i++) {
    const col = i % cols;
    const row = Math.floor(i / cols);

    /* 格内随机偏移，避免过于整齐 */
    const jitterX = (_hash(i, 1) - 0.5) * cellW * 0.35;
    const jitterY = (_hash(i, 2) - 0.5) * cellH * 0.30;
    const rRot = _hash(i, 3);
    const rot = (rRot < 0.4) ? -3 + rRot * 12 : (rRot < 0.8) ? _hash(i, 5) * 10 - 5 : _hash(i, 6) * 16 - 8;
    const scale = 0.88 + _hash(i, 4) * 0.14;
    const zIndex = i + 1;

    pos.push({
      left: area.left + col * cellW + cellW / 2 + jitterX,
      top:  area.top  + row * cellH + cellH / 2 + jitterY,
      rotation: rot, scale, zIndex,
    });
  }
  return pos;
}

function renderGame() {
  const el = document.getElementById('page-game');
  if (!el) return;
  const state = App.state;
  const pcs = state.postcards || [];
  const has = pcs.length > 0;

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

  /* ── 卡片 ── */
  let cards = '';
  if (has) {
    const positions = scatterPositions(pcs.length);
    cards = pcs.map((pc, i) => {
      const pt = positions[i];
      return `<div class="pc-card"
                style="left:${pt.left.toFixed(1)}%;top:${pt.top.toFixed(1)}%;transform:translate(-50%,-50%)rotate(${pt.rotation.toFixed(1)}deg)scale(${pt.scale.toFixed(2)});z-index:${pt.zIndex}"
                onclick="App.showPostcardDetail(pc__${i})">
          <div class="pc-card-sh"></div>
          <div class="pc-card-bd">
            <div class="pc-fr">${App._imgHtml(pc)}</div>
            <div class="pc-body">
              <div class="loc">${App._e(pc.place||'')}</div>
              <div class="tit">${App._e(pc.title||'无题')}</div>
            </div>
          </div>
        </div>`;
    }).join('');
    window._tdPCs = pcs;
    cards = cards.replace(/pc__(\d+)/g, (_, i) => `window._tdPCs[${i}]`);
  }

  el.innerHTML = `
    <div class="desk-surface">
      ${deskItems}
      <div class="desk-grain"></div>
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
