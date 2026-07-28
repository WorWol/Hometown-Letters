/* ===== 记忆页 (Godot MemoryScene) ===== */

function renderMemories() {
  const el = document.getElementById('page-memories');
  if (!el) return;
  const memories = App.state.memories || [];
  const profile = App.state.pastSelfProfile || {};
  const places = profile.latent_place_affinities || [];
  const sensory = profile.sensory_biases || [];
  const hasProfile = places.length || sensory.length;
  window._memories = memories;
  el.innerHTML = `
    <div class="memory-grid">
      <section class="memory-list-panel paper-panel">
        <div class="panel-heading"><div><span class="section-kicker">${memories.length} MEMORIES</span><h2>记忆片段</h2></div><button class="btn btn-pri" onclick="showMemForm()">记录记忆</button></div>
        ${memories.length ? `<div class="memory-list">${memories.map((memory, index) => `
          <button class="memory-item" onclick="showMemDetail(window._memories[${index}])"><span class="memory-thread" aria-hidden="true"></span><span class="memory-copy"><strong>${App._e((memory.text || '').slice(0, 80))}</strong><small>${memory.timestamp ? new Date(memory.timestamp).toLocaleString('zh-CN') : ''}${memory.analysisStatus ? ` · ${_as(memory.analysisStatus)}` : ''}</small><span class="modal-tags">${(memory.tags || []).map(tag => `<span class="tag tag-g">${App._e(tag)}</span>`).join('')}</span></span></button>`).join('')}</div>` : `<div class="visual-empty page-empty-scene memory-empty"><img src="assets/workbench/empty-memory-journal.webp" alt="傍晚桌面上的布面手账、旧照片与压花" onerror="this.closest('.page-empty-scene').classList.add('image-missing');this.remove()"><div><h3>还没有记忆</h3><p>可以记录一个地方、一种气味或某个瞬间。</p><button class="btn btn-pri" onclick="showMemForm()">记录第一条记忆</button></div></div>`}
      </section>
      <aside class="profile-card memory-profile-card dark-panel" aria-label="过去的我">
        <div class="profile-portrait" aria-hidden="true"><div class="profile-frame"><div class="profile-silhouette"><span>我</span></div></div></div>
        <span class="section-kicker">THE PAST ME</span><h2>过去的我</h2>
        ${hasProfile ? `<div class="profile-groups">
          ${places.length ? `<div><h3>总会想起的地方</h3><div class="modal-tags">${places.slice(0, 6).map(item => `<span class="tag">${App._e(item.name || '')}</span>`).join('')}</div></div>` : ''}
          ${sensory.length ? `<div><h3>风、光和气味</h3><div class="modal-tags">${sensory.slice(0, 6).map(item => `<span class="tag">${App._e(item.name || '')}</span>`).join('')}</div></div>` : ''}
        </div>` : ''}
      </aside>
    </div>`;
}

function _as(s) {
  switch(s){case'pending':return'正在分析…';case'completed':return'已整理';case'failed':return'分析失败';default:return'';}
}

function showMemDetail(m) {
  const e = document.querySelector('.modal'); if(e) e.remove();
  const o = document.createElement('div'); o.className='modal';
  o.onclick=e=>{if(e.target===o)o.remove();};
  o.innerHTML = `<div class="modal-pnl"><div class="modal-hd"><h3>记忆详情</h3><button class="modal-cl" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button></div>
    <div class="modal-meta">${m.timestamp?new Date(m.timestamp).toLocaleString('zh-CN'):''}${m.analysisStatus?' · '+_as(m.analysisStatus):''}</div>
    <div class="modal-bd">${App._e(m.text)}</div>
    ${m.summary?`<div class="modal-poem" style="font-style:normal;color:var(--ink-soft);">${App._e(m.summary)}</div>`:''}
    ${m.tags&&m.tags.length>0?`<div class="modal-tags">${m.tags.map(t=>`<span class="tag">${App._e(t)}</span>`).join('')}</div>`:''}
    <div class="modal-ft"><button class="btn btn-sec" onclick="this.closest('.modal').remove()">关闭</button></div></div>`;
  document.body.appendChild(o);
}

function showMemForm() {
  const e = document.querySelector('.modal'); if(e) e.remove();
  const o = document.createElement('div'); o.className='modal';
  o.onclick=e=>{if(e.target===o)o.remove();};
  o.innerHTML = `<div class="modal-pnl"><div class="modal-hd"><h3>记录记忆</h3><button class="modal-cl" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button></div>
    <div style="padding:14px 24px 20px;">
      <div class="fg" style="margin-bottom:12px;"><label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--ink-soft);">记忆内容</label>
        <textarea class="inp inp-ta" id="mem-text" rows="4" placeholder="写下想记录的地方、气味或瞬间"></textarea></div>
      <div style="display:flex;gap:12px;">
        <div class="fg" style="flex:1;"><label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--ink-soft);">标签（用逗号分隔）</label><input class="inp" id="mem-tags" placeholder="例如：家、学校、夏天"></div>
        <div class="fg" style="flex:1;"><label style="display:block;font-size:13.5px;margin-bottom:5px;color:var(--ink-soft);">地点（可选）</label><input class="inp" id="mem-place" placeholder="例如：秀流公园"></div>
      </div>
      <button class="btn btn-pri" onclick="saveMem()" id="mem-btn" style="margin-top:14px;">保存记忆</button>
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
  if(!t.value.trim()){s.textContent='请输入记忆内容';return;}
  b.disabled = true; s.textContent = '正在保存…';
  try {
    const tags = tg.value.trim()?tg.value.split(/[,，、、]/).map(x=>x.trim()).filter(Boolean):[];
    const r = await api.saveMemory(t.value.trim(), tags, pl.value.trim());
    if(r.ok) {
      const sr = await api.getState();
      if(sr.ok) App.applyState(sr.data);
      document.querySelector('.modal')?.remove(); App.showToast('记忆已保存'); renderMemories();
    } else { s.textContent = App.friendlyError(r.error, '保存失败，请稍后重试'); }
  } catch(e) { s.textContent = App.friendlyError(e, '保存失败，请稍后重试'); console.error(e); }
  b.disabled = false;
}
