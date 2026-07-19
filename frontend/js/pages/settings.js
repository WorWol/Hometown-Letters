/* 设置页。 */

function renderSettings() {
  const el = document.getElementById('page-settings');
  if (!el) return;
  const state = App.state;
  const user = Auth.getUser();
  el.innerHTML = `
    <div class="settings-grid">
      <section class="paper-panel setting-card account-card">
        <span class="section-kicker">ACCOUNT</span><h2>账户</h2>
        <div class="account-person"><span class="mailbox-avatar">${App._e((user?.username || '访')[0])}</span><div><strong>${App._e(user?.username || '访客')}</strong><small>${user ? '信箱已经上锁保管' : '当前正在随便看看'}</small></div></div>
        ${user ? '<button class="btn btn-dng" onclick="doLogout()">退出登录</button>' : '<button class="btn btn-pri" onclick="showAuthGate()">登录信箱</button>'}
      </section>
      <section class="paper-panel setting-card hometown-card">
        <span class="section-kicker">HOMETOWN</span><h2>故乡地址</h2>
        <div class="form-grid two">
          <label>省<input class="inp" id="s-prov" value="${App._e(state.hometown?.province || '湖南')}"></label>
          <label>市<input class="inp" id="s-city" value="${App._e(state.hometown?.city || '郴州')}"></label>
          <label>区 / 县<input class="inp" id="s-county" value="${App._e(state.hometown?.county || '资兴')}"></label>
          <label>故乡名称<input class="inp" id="s-name" value="${App._e(state.hometown?.hometownName || '资兴')}"></label>
        </div>
        <div class="setting-actions"><button class="btn btn-pri" onclick="saveHome()">保存故乡</button><span class="st" id="s-home-st" aria-live="polite">&nbsp;</span></div>
      </section>
      <section class="dark-panel setting-card status-card">
        <span class="section-kicker">JOURNEY STATUS</span><h2>旅程状态</h2>
        <div class="stat-grid four"><div><strong>${state.currentDay || 0}</strong><span>天</span></div><div><strong>${(state.postcards || []).length}</strong><span>明信片</span></div><div><strong>${(state.memories || []).length}</strong><span>记忆</span></div><div><strong>${(state.letters || []).length}</strong><span>信件</span></div></div>
      </section>
      <section class="paper-panel setting-card connection-card">
        <span class="section-kicker">CONNECTION</span><h2>邮路连接</h2><p>检查网页与故乡来信服务是否连通。</p>
        <div class="setting-actions"><button class="btn btn-sec" onclick="checkBack()">检查连接</button><span class="st" id="s-backend-st" aria-live="polite">&nbsp;</span></div>
      </section>
    </div>`;
}

async function saveHome() {
  const status = document.getElementById('s-home-st');
  status.textContent = '保存中…';
  try {
    const response = await api.initHometown({ province: document.getElementById('s-prov').value.trim(), city: document.getElementById('s-city').value.trim(), county: document.getElementById('s-county').value.trim(), hometown_name: document.getElementById('s-name').value.trim() });
    if (!response.ok) throw new Error(response.error || '保存失败');
    App.state.hometown = response.data.hometown;
    App.state.profile = response.data.profile;
    App.state.initialized = true;
    App.syncShell();
    status.textContent = '已保存';
    App.showToast('故乡地址已更新');
  } catch (error) { status.textContent = error.message || '网络错误'; }
}

async function checkBack() {
  const status = document.getElementById('s-backend-st');
  status.textContent = '检查中…';
  try { const response = await api.getMe(); status.textContent = response.ok ? '邮路畅通' : '连接异常'; }
  catch (error) { status.textContent = '无法连接'; }
}
