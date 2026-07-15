/* ===== 记忆页 (Godot MemoryScene) ===== */

function renderMemories() {
  const el = document.getElementById('page-memories');
  if (!el) return;
  const ms = App.state.memories||[];
  const prof = App.state.pastSelfProfile||{};
  const places = prof.latent_place_affinities||[];
  const sensory = prof.sensory_biases||[];
  const identity = prof.identity_signals||[];
  const recent = prof.recent_memory_signals||[];
  const hasProf = places.length>0||sensory.length>0;

  const profHTML = hasProf ? `
    <div class="profile">
      <div class="s-tit">过去的我</div>
      <p class="smr">${App._e(prof.summary||'有些印象还很轻，但已经在心里慢慢留下来了。')}</p>
      ${places.length>0?`<div class="s-tit" style="margin-top:0;font-size:13px;">总会想起的地方</div>
        <div class="pg" style="margin-bottom:10px;">${places.slice(0,6).map(p=>`<span class="pi">${App._e(p.name||'')}</span>`).join('')}</div>`:''}
      ${sensory.length>0?`<div class="s-tit" style="font-size:13px;">风、光和气味</div>
        <div class="pg" style="margin-bottom:10px;">${sensory.slice(0,6).map(s=>`<span class="pi pi-g">${App._e(s.name||'')}</span>`).join('')}</div>`:''}
      ${identity.length>0?`<div class="s-tit" style="font-size:13px;">过去的我是个怎样的小孩</div>
        ${identity.slice(0,4).map(id=>`<div class="pp">· ${_il(id.name||'')}</div>`).join('')}`:''}
      ${recent.length>0?`<div class="s-tit" style="font-size:13px;margin-top:10px;">慢慢留了下来的</div>
        ${recent.slice(0,4).map(r=>`<div class="pp">· 最近总会想起${App._e(r.name||'')}</div>`).join('')}`:''}
    </div>` : `<div class="card" style="margin-bottom:14px;"><div class="card-ttl">过去的我</div>
      <p style="color:var(--dk-muted);font-size:13.5px;">写下一些记忆后，它会慢慢在这里浮现。</p></div>`;

  el.innerHTML = `
    <div class="pg-hd">
      <h2>记忆册</h2>
      <p>${App.state.hometown?.hometownName?`· ${App._e(App.state.hometown.hometownName)} `:''}这里放着我想起来的一些事。</p>
    </div>
    <div class="mem-lay">
      <div class="mem-main">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px;">
          <span style="font-size:14px;color:var(--dk-sec);font-weight:500;">${ms.length} 条记忆</span>
          <button class="btn btn-pri" onclick="showMemForm()">记下一件小事</button>
        </div>
        ${ms.length===0?`<div class="card" style="text-align:center;padding:36px 20px;"><p style="color:var(--dk-muted);">还没有记下任何事。</p></div>`
          :`<div>${ms.map((m,i)=>`
            <div class="card mem-item" onclick="showMemDetail(mem__${i})">
              <div class="tx">${App._e(m.text)}</div>
              <div class="mt">${m.tags&&m.tags.length>0?`标签：${m.tags.join('、')} · `:''}${m.timestamp?new Date(m.timestamp).toLocaleString('zh-CN'):''}${m.analysisStatus?` · ${_as(m.analysisStatus)}`:''}</div>
              ${m.tags&&m.tags.length>0?`<div class="tg">${m.tags.map(t=>`<span class="tag tag-g">${App._e(t)}</span>`).join('')}</div>`:''}
            </div>`).join('')}</div>`}
      </div>
      <div class="mem-side">${profHTML}</div>
    </div>`;
  window._mems = ms;
  el.querySelectorAll('[onclick*="mem__"]').forEach(el2=>{
    const m = el2.getAttribute('onclick').match(/mem__(\d+)/);
    if (m) el2.setAttribute('onclick',`showMemDetail(window._mems[${parseInt(m[1])}])`);
  });
}

function _il(n) {
  if(!n) return '慢慢也成了过去的我的一部分。';
  if(n.includes('不爱说')||n.includes('安静')) return '不太会一下子说很多话。';
  if(n.includes('细')||n.includes('小')) return '会把很小的事情记很久。';
  if(n.includes('走')||n.includes('停')||n.includes('看')) return '总会在热闹结束后多停一下。';
  if(n.includes('风')||n.includes('空气')||n.includes('水')) return '会被风和空气里的变化悄悄打动。';
  return `${n}，慢慢也成了过去的我的一部分。`;
}
function _as(s) {
  switch(s){case'pending':return'正在整理…';case'completed':return'已归档';case'failed':return'稍后重试';default:return'';}
}

function showMemDetail(m) {
  const e = document.querySelector('.modal'); if(e) e.remove();
  const o = document.createElement('div'); o.className='modal';
  o.onclick=e=>{if(e.target===o)o.remove();};
  o.innerHTML = `<div class="modal-pnl"><div class="modal-hd"><h3>这段记忆</h3><button class="modal-cl" onclick="this.closest('.modal').remove()">x</button></div>
    <div class="modal-meta">${m.timestamp?new Date(m.timestamp).toLocaleString('zh-CN'):''}${m.analysisStatus?' · '+_as(m.analysisStatus):''}</div>
    <div class="modal-bd">${App._e(m.text)}</div>
    ${m.summary?`<div class="modal-poem" style="font-style:normal;color:var(--dk-sec);">${App._e(m.summary)}</div>`:''}
    ${m.tags&&m.tags.length>0?`<div class="modal-tags">${m.tags.map(t=>`<span class="tag">${App._e(t)}</span>`).join('')}</div>`:''}
    <div class="modal-ft"><button class="btn btn-sec" onclick="this.closest('.modal').remove()">关闭</button></div></div>`;
  document.body.appendChild(o);
}

function showMemForm() {
  const e = document.querySelector('.modal'); if(e) e.remove();
  const o = document.createElement('div'); o.className='modal';
  o.onclick=e=>{if(e.target===o)o.remove();};
  o.innerHTML = `<div class="modal-pnl"><div class="modal-hd"><h3>记下一件小事</h3><button class="modal-cl" onclick="this.closest('.modal').remove()">x</button></div>
    <div style="padding:14px 24px 20px;">
      <div class="fg" style="margin-bottom:12px;"><label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--dk-sec);">什么小事？</label>
        <textarea class="inp inp-ta" id="mem-text" rows="4" placeholder="今天想起了什么？某个地方、某种气味、某个瞬间……"></textarea></div>
      <div style="display:flex;gap:12px;">
        <div class="fg" style="flex:1;"><label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--dk-sec);">标签（逗号分隔）</label><input class="inp" id="mem-tags" placeholder="如：家、学校、夏天"></div>
        <div class="fg" style="flex:1;"><label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--dk-sec);">地点（可选）</label><input class="inp" id="mem-place" placeholder="如：秀流公园"></div>
      </div>
      <button class="btn btn-pri" onclick="saveMem()" id="mem-btn" style="margin-top:14px;">保存这段记忆</button>
      <div class="st" id="mem-status">&nbsp;</div>
    </div></div>`;
  document.body.appendChild(o);
}

async function saveMem() {
  const t = document.getElementById('mem-text');
  const tg = document.getElementById('mem-tags');
  const pl = document.getElementById('mem-place');
  const s = document.getElementById('mem-status');
  const b = document.getElementById('mem-btn');
  if(!t.value.trim()){s.textContent='先写下一些话';return;}
  b.disabled = true; s.textContent = '收下这段记忆…';
  try {
    const tags = tg.value.trim()?tg.value.split(/[,，、、]/).map(x=>x.trim()).filter(Boolean):[];
    const r = await api.saveMemory(t.value.trim(), tags, pl.value.trim());
    if(r.ok) {
      const sr = await api.getState();
      if(sr.ok) App.applyState(sr.data);
      document.querySelector('.modal')?.remove(); App.showToast('记忆已收好'); renderMemories();
    } else { s.textContent = r.error||'未能保存'; }
  } catch(e) { s.textContent = '网络错误'; console.error(e); }
  b.disabled = false;
}
