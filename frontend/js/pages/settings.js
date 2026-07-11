/* ===== 设置页 (Godot SettingsScene) ===== */

function renderSettings() {
  const el = document.getElementById('page-settings');
  if (!el) return;
  const s = App.state;
  const useV2 = App._authMode === 'v2';
  const userInfo = useV2 ? Auth.getUser() : null;

  el.innerHTML = `
    <div class="pg-hd">
      <div class="eyebrow">Settings</div>
      <h2>⚙️ 设置</h2>
      <p>故乡信息、游戏状态和管理。</p>
    </div>

    ${userInfo ? `
    <div class="set-sec">
      <h3>👤 账户</h3>
      <div class="set-row"><label>用户名</label><span style="font-size:14px;color:var(--dk-text);">${App._e(userInfo.username)}</span></div>
      <button class="btn btn-dng" onclick="doLogout()" style="margin-top:8px;">退出登录</button>
      <p class="set-ht">退出登录后可在本地体验模式继续使用。</p>
    </div>` : ''}

    <div class="set-sec">
      <h3>🏡 故乡</h3>
      <div class="set-row"><label>省</label><input class="inp" id="s-prov" value="${App._e(s.hometown?.province||'湖南')}"></div>
      <div class="set-row"><label>市</label><input class="inp" id="s-city" value="${App._e(s.hometown?.city||'郴州')}"></div>
      <div class="set-row"><label>区/县</label><input class="inp" id="s-county" value="${App._e(s.hometown?.county||'资兴')}"></div>
      <div class="set-row"><label>故乡名称</label><input class="inp" id="s-name" value="${App._e(s.hometown?.hometownName||'资兴')}"></div>
      <button class="btn btn-pri" onclick="saveHome()" style="margin-top:8px;">保存</button>
      <div class="st" id="s-home-st">&nbsp;</div>
    </div>
    <div class="set-sec">
      <h3>📊 状态</h3>
      <div class="set-row"><label>当前天数</label><span style="font-size:14px;color:var(--dk-text);">第 ${s.currentDay||0} 天</span></div>
      <div class="set-row"><label>明信片</label><span style="font-size:14px;color:var(--dk-text);">${(s.postcards||[]).length} 张</span></div>
      <div class="set-row"><label>记忆</label><span style="font-size:14px;color:var(--dk-text);">${(s.memories||[]).length} 条</span></div>
      <div class="set-row"><label>信件</label><span style="font-size:14px;color:var(--dk-text);">${(s.letters||[]).length} 封</span></div>
    </div>
    <div class="set-sec">
      <h3>⚠️ 管理</h3>
      <button class="btn btn-dng" onclick="resetAll()">重置存档</button>
      <p class="set-ht">所有明信片、记忆和信件将被清除。</p>
      <div class="st" id="s-reset-st">&nbsp;</div>
    </div>
    <div class="set-sec">
      <h3>🔌 后端</h3>
      <div class="set-row"><label>地址</label><input class="inp" id="s-backend" value="http://127.0.0.1:8787"></div>
      <button class="btn btn-sec" onclick="checkBack()">检查连接</button>
      <div class="st" id="s-backend-st">&nbsp;</div>
    </div>`;
}

async function saveHome() {
  const s = document.getElementById('s-home-st');
  const data = {
    province: document.getElementById('s-prov').value,
    city: document.getElementById('s-city').value,
    county: document.getElementById('s-county').value,
    hometown_name: document.getElementById('s-name').value,
  };

  try {
    const useV2 = App._authMode === 'v2';
    const r = useV2
      ? await api.v2InitHometown(data)
      : await api.initHometown({ user_id: 'default', ...data });
    if (r.ok) {
      App.state.hometown = r.data.hometown;
      App.state.profile = r.data.profile;
      App.state.initialized = true;
      s.textContent = '✅ 已保存';
      App.showToast('已更新 🏡');
    } else {
      s.textContent = '❌ 失败';
    }
  } catch (e) {
    s.textContent = '❌ 网络错误';
    console.error(e);
  }
}

async function checkBack() {
  const s = document.getElementById('s-backend-st'); s.textContent = '检查中…';
  try { const r = await api.health(); s.textContent = r.ok ? '✅ 后端正常' : '❌ 异常'; } catch (e) { s.textContent = '❌ 无法连接'; }
}

async function resetAll() {
  if (!confirm('确定重置？不可撤销。')) return;
  if (!confirm('再次确认：所有数据将被清除。')) return;
  const s = document.getElementById('s-reset-st');
  try {
    await api.reset();
    App.state = { initialized: false, currentDay: 0, hometown: {}, profile: {}, postcards: [], letters: [], memories: [], pastSelfProfile: {} };
    s.textContent = '✅ 已重置'; App.showToast('已重置 🍃'); renderSettings(); renderGame();
  } catch (e) { s.textContent = '❌ 失败'; console.error(e); }
}
