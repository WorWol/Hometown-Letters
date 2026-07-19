/* ===== 设置页 ===== */

function renderSettings() {
  const el = document.getElementById('page-settings');
  if (!el) return;
  const s = App.state;
  const userInfo = Auth.getUser();

  el.innerHTML = `
    <div class="pg-hd">
      <div class="eyebrow">Settings</div>
      <h2>设置</h2>
      <p>故乡信息、游戏状态和管理。</p>
    </div>

    ${userInfo ? `
    <div class="set-sec">
      <h3>账户</h3>
      <div class="set-row"><label>用户名</label><span style="font-size:14px;color:var(--px-ink);">${App._e(userInfo.username)}</span></div>
      <button class="btn btn-dng" onclick="doLogout()" style="margin-top:8px;">退出登录</button>
    </div>` : ''}

    <div class="set-sec">
      <h3>故乡</h3>
      <div class="set-row"><label>省</label><input class="inp" id="s-prov" value="${App._e(s.hometown?.province||'湖南')}"></div>
      <div class="set-row"><label>市</label><input class="inp" id="s-city" value="${App._e(s.hometown?.city||'郴州')}"></div>
      <div class="set-row"><label>区/县</label><input class="inp" id="s-county" value="${App._e(s.hometown?.county||'资兴')}"></div>
      <div class="set-row"><label>故乡名称</label><input class="inp" id="s-name" value="${App._e(s.hometown?.hometownName||'资兴')}"></div>
      <button class="btn btn-pri" onclick="saveHome()" style="margin-top:8px;">保存</button>
      <div class="st" id="s-home-st">&nbsp;</div>
    </div>
    <div class="set-sec">
      <h3>状态</h3>
      <div class="set-row"><label>当前天数</label><span style="font-size:14px;color:var(--px-ink);">第 ${s.currentDay||0} 天</span></div>
      <div class="set-row"><label>明信片</label><span style="font-size:14px;color:var(--px-ink);">${s.postcardCount} / ${s.postcardLimit} 张</span></div>
      <div class="set-row"><label>记忆</label><span style="font-size:14px;color:var(--px-ink);">${(s.memories||[]).length} 条</span></div>
      <div class="set-row"><label>信件</label><span style="font-size:14px;color:var(--px-ink);">${(s.letters||[]).length} 封</span></div>
    </div>
    <div class="set-sec">
      <h3>后端</h3>
      <div class="set-row"><label>地址</label><input class="inp" id="s-backend" value="${App._e(window.location.origin)}" readonly></div>
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
    const r = await api.initHometown(data);
    if (r.ok) {
      App.state.hometown = r.data.hometown;
      App.state.profile = r.data.profile;
      App.state.initialized = true;
      s.textContent = '已保存';
      App.showToast('已更新');
    } else {
      s.textContent = '失败';
    }
  } catch (e) {
    s.textContent = '网络错误';
    console.error(e);
  }
}

async function checkBack() {
  const s = document.getElementById('s-backend-st');
  s.textContent = '检查中…';
  try {
    const r = await api.getMe();
    s.textContent = r.ok ? '后端正常' : '异常';
  } catch (e) {
    s.textContent = '无法连接';
  }
}
