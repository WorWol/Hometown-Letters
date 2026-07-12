/* ===== 桌面场景 — 明信片自然散落桌面 (Godot GameScene) ===== */

let _gameBusy = false;

/* 高质量确定性"伪随机"哈希 */
function _hash(i, salt) {
  let h = ((i + 1) * 2654435761 + salt * 734280139) >>> 0;
  h ^= h >> 13;
  h *= 0x5bd1e995;
  h ^= h >> 15;
  return (h >>> 0) % 100000 / 100000;
}

/* 自然散射算法 —— 模拟多堆卡片散落在桌面 */
function scatterPositions(count) {
  const pos = [];
  if (count === 0) return pos;

  /* 桌面上 3 个"落点区域"（中心偏右是当前在读区，左上是被推到一边的） */
  const zones = [
    { cx: 48, cy: 40, rx: 12, ry: 11, weight: 0.35 },  // 中间偏右：正在看的
    { cx: 28, cy: 52, rx: 10, ry: 9,  weight: 0.30 },  // 左中：推开的一叠
    { cx: 62, cy: 30, rx: 9,  ry: 8,  weight: 0.20 },  // 右上：零星散落
    { cx: 42, cy: 68, rx: 11, ry: 7,  weight: 0.15 },  // 中下：推到桌边
  ];

  /* 按权重分配卡片到各区域 */
  const zoneCards = zones.map(() => []);
  for (let i = 0; i < count; i++) {
    let r = _hash(i, 10);
    let acc = 0;
    let zi = 0;
    for (let z = 0; z < zones.length; z++) {
      acc += zones[z].weight;
      if (r <= acc) { zi = z; break; }
    }
    zoneCards[zi].push(i);
  }

  /* 为每张卡在区域内生成位置 */
  for (let i = 0; i < count; i++) {
    const z = zoneCards.findIndex(arr => arr.includes(i));
    const zone = zones[z >= 0 ? z : 0];
    const localIdx = zoneCards[z >= 0 ? z : 0].indexOf(i);

    /* 区域内位置：用高斯混合模拟簇内自然分布 */
    const u1 = _hash(i, 1);
    const u2 = _hash(i, 2);
    /* Box-Muller 风格的簇内散布 */
    const rSpread = Math.sqrt(-2 * Math.log(Math.max(u1, 0.001)));
    const theta = u2 * Math.PI * 2;
    const dx = rSpread * Math.cos(theta) * zone.rx * 0.55;
    const dy = rSpread * Math.sin(theta) * zone.ry * 0.55;
    const left = zone.cx + dx;
    const top  = zone.cy + dy;

    /* 旋转角度：少数卡片近乎正放，大部分歪得比较厉害 */
    const rRot = _hash(i, 3);
    let rotation;
    if (rRot < 0.25) {
      /* 25% 卡片接近水平 */
      rotation = -4 + rRot / 0.25 * 8;
    } else if (rRot < 0.75) {
      /* 50% 卡片有明显倾斜 */
      rotation = (rRot < 0.5 ? -1 : 1) * (6 + _hash(i, 5) * 14);
    } else {
      /* 25% 卡片歪得很大，像随手一扔 */
      rotation = (rRot < 0.875 ? -1 : 1) * (8 + _hash(i, 6) * 16);
    }

    /* 大小微调，模拟纸张厚薄和层次感 */
    const scale = 0.85 + _hash(i, 4) * 0.20;

    /* z 序：区域内按生成顺序叠压，最后生成的放在上面 */
    const zIndex = localIdx + 1;

    pos.push({ left, top, rotation, scale, zIndex, zone: z >= 0 ? z : 0 });
  }

  return pos;
}

function renderGame() {
  const el = document.getElementById('page-game');
  if (!el) return;
  const state = App.state;
  const pcs = state.postcards || [];
  const has = pcs.length > 0;

  let cards = '';
  if (has) {
    const show = [...pcs];
    const positions = scatterPositions(show.length);

    cards = show.map((pc, i) => {
      const pt = positions[i];
      const z = (pt.zone + 1) * 100 + pt.zIndex;
      const prev = (pc.body || '').slice(0, 80);
      return `<div class="pc-card"
                style="left:${pt.left.toFixed(1)}%;top:${pt.top.toFixed(1)}%;transform:translate(-50%,-50%)rotate(${pt.rotation.toFixed(1)}deg)scale(${pt.scale.toFixed(2)});z-index:${z}"
                onclick="App.showPostcardDetail(pc__${i})">
          <div class="pc-card-sh"></div>
          <div class="pc-card-bd">
            <div class="pc-fr">
              <div class="pc-img">${App._imgHtml(pc, {small:true})}</div>
            </div>
            <div class="pc-body">
              <div class="loc">${App._e(pc.place||'')}</div>
              <div class="tit">${App._e(pc.title||'无题')}</div>
              <div class="prev">${App._e(prev)}${prev.length>=80?'…':''}</div>
            </div>
          </div>
        </div>`;
    }).join('');
    window._tdPCs = show;
    cards = cards.replace(/pc__(\d+)/g, (_, i) => `window._tdPCs[${i}]`);
  }

  el.innerHTML = `
    <div class="desk-bar">
      <span class="day">桌面 · 第 ${state.currentDay||0} 天</span>
      <span class="hint">${has ? `桌上有 ${pcs.length} 封来信散落着` : '桌上还没有新的来信'}</span>
    </div>
    <div class="pc-stack">
      ${has ? cards : `
        <div class="stack-empty">
          <h3>今天的桌面还没有新的明信片</h3>
          <p>去[写信]或点 NEXT DAY 试试</p>
          <button class="btn btn-pri" style="margin-top:16px" onclick="App.navigate('write_letter')">写第一封信</button>
        </div>`}
    </div>
    <div class="desk-foot">
      <div class="meta"><span class="hint" id="g-status">${has ? `累计 ${state.postcards.length} 张` : ''}</span></div>
      <button class="btn btn-big" onclick="nextDay()" id="g-nextday" ${_gameBusy?'disabled':''}>${_gameBusy?'收信中…':'NEXT DAY'}</button>
    </div>`;
}

async function nextDay() {
  if (_gameBusy) return;
  _gameBusy = true;
  const btn = document.getElementById('g-nextday');
  const st = document.getElementById('g-status');
  if (btn) { btn.disabled = true; btn.textContent = '收信中…'; }
  if (st) st.textContent = '正在寄出明信片…';

  try {
    if (!App.state.initialized) {
      const r = await api.initHometown({ user_id:'default', province:'湖南', city:'郴州', county:'资兴', hometown_name:'资兴' });
      if (r.ok) { App.state.initialized = true; App.state.hometown = r.data.hometown; App.state.profile = r.data.profile; }
    }
    const lr = await api.sendLetter('今天天气不错，我想去走走看看。', App.state.hometown?.hometownName||'资兴', '平静');
    if (lr.ok) {
      const sr = await api.getState();
      if (sr.ok) { App.state.postcards = sr.data.postcards||[]; App.state.currentDay = sr.data.current_day||0; }
      if (st) st.textContent = '新的明信片落在桌上';
      App.showToast('新的明信片已到达');
      if (lr.data) setTimeout(() => App.showPostcardDetail(lr.data), 500);
    } else {
      if (st) st.textContent = lr.error||'明信片没有送到';
    }
  } catch(e) {
    if (st) st.textContent = '网络错误，检查后端是否启动';
    console.error(e);
  }
  _gameBusy = false;
  if (btn) { btn.disabled = false; btn.textContent = 'NEXT DAY'; }
  renderGame();
}
