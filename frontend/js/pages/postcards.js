/* ===== 明信片收藏页 (Godot PostcardsScene) ===== */

function renderPostcards() {
  const el = document.getElementById('page-postcards');
  if (!el) return;
  const all = App.state.postcards||[];
  const filterText = (document.getElementById('pc-filter')?.value||'').trim().toLowerCase();
  const f = filterText ? all.filter(pc => `${pc.place||''} ${pc.mood||''} ${(pc.tags||[]).join(' ')} ${pc.title||''} ${pc.body||''}`.toLowerCase().includes(filterText)) : all;

  el.innerHTML = `
    <div class="pg-hd">
      <h2>明信片收藏</h2>
      <p>所有已经收到的明信片都在这里，像一本不断生长的画册。</p>
    </div>
    <div class="pc-g-hd">
      <span style="font-size:13.5px;color:var(--px-ink-muted);">${f.length} 张明信片</span>
      <input class="inp" id="pc-filter" placeholder="地点 / 标签 / 情绪" value="${App._e(filterText)}" oninput="renderPostcards()">
    </div>
    ${f.length===0?`<div class="g-empty"><p>${filterText?'没有匹配的明信片':'这里暂时是空的。去桌面推进几天吧。'}</p></div>`
      :`<div class="pc-g">${f.map((pc,i)=>`
        <div class="g-card" onclick="App.showPostcardDetail(pcf_${i})">
          ${pc.imageThumbUrl?`<img src="${App._e(pc.imageThumbUrl)}" alt="" loading="lazy" decoding="async" onerror="this.style.display='none'">`:''}
          <div class="info">
            <div class="ti">${App._e(pc.title||'无题')}</div>
            <div class="lo">${App._e(pc.place||'')}${pc.createdAt?' · '+new Date(pc.createdAt).toLocaleDateString('zh-CN'):''}</div>
          </div>
        </div>`).join('')}</div>`}
  `;
  window._pcf = f;
  el.querySelectorAll('[onclick*="pcf_"]').forEach(el2=>{
    const m = el2.getAttribute('onclick').match(/pcf_(\d+)/);
    if (m) el2.setAttribute('onclick',`App.showPostcardDetail(window._pcf[${parseInt(m[1])}])`);
  });
}
