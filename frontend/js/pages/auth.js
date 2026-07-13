/* ===== 登录/注册页面 ===== */

function renderAuthPage(mode) {
  const el = document.getElementById('page-auth');
  const isLogin = mode === 'login';
  el.innerHTML = `
    <div class="auth-container">
      <!-- 顶部插画 -->
      <div class="auth-illust">
        <div class="auth-postbox">
          <div class="auth-postbox-body">
            <div class="auth-postbox-slot"></div>
            <div class="auth-postbox-label">LETTERS</div>
          </div>
          <div class="auth-postbox-stand"></div>
        </div>
        <div class="auth-floating-letter l1">✉</div>
        <div class="auth-floating-letter l2">✉</div>
        <div class="auth-floating-letter l3">✉</div>
      </div>

      <div class="auth-card">
        <!-- 蜡封装饰 -->
        <div class="auth-seal"></div>

        <div class="auth-header">
          <h1>故乡来信</h1>
          <p class="auth-subtitle">H O M E T O W N &nbsp; L E T T E R S</p>
          <div class="auth-divider"><span>给过去的自己写一封信</span></div>
        </div>

        <div class="auth-tabs">
          <button class="auth-tab ${isLogin ? 'active' : ''}" onclick="renderAuthPage('login')">登录</button>
          <button class="auth-tab ${!isLogin ? 'active' : ''}" onclick="renderAuthPage('register')">注册</button>
        </div>

        <form class="auth-form" onsubmit="handleAuth(event, '${mode}')">
          <div class="auth-field">
            <label>用户名</label>
            <div class="auth-input-wrap">
              <span class="auth-input-icon">
                <svg width="14" height="14" viewBox="0 0 14 14"><rect x="2" y="3" width="10" height="9" rx="1.5" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="6.5" r="2" fill="none" stroke="currentColor" stroke-width="1"/><path d="M3.5 9.5Q7 7.5 10.5 9.5" fill="none" stroke="currentColor" stroke-width="1"/></svg>
              </span>
              <input type="text" id="auth-username" class="inp" placeholder="你的名字" required minlength="2" maxlength="32">
            </div>
          </div>
          <div class="auth-field">
            <label>密码</label>
            <div class="auth-input-wrap">
              <span class="auth-input-icon">
                <svg width="14" height="14" viewBox="0 0 14 14"><rect x="2.5" y="5" width="9" height="7" rx="1" fill="none" stroke="currentColor" stroke-width="1.2"/><path d="M5 5V3.5a2 2 0 0 1 4 0V5" fill="none" stroke="currentColor" stroke-width="1.2"/><circle cx="7" cy="8.5" r="1" fill="currentColor"/></svg>
              </span>
              <input type="password" id="auth-password" class="inp" placeholder="••••••••" required minlength="4">
            </div>
          </div>
          <div class="auth-err" id="auth-error" style="display:none;"></div>
          <button type="submit" class="auth-submit" id="auth-submit">
            <span>${isLogin ? '打开信箱' : '寄出第一封信'}</span>
          </button>
        </form>

        <div class="auth-demo">
          <a onclick="skipAuth()">先随便看看</a>
        </div>

        <!-- 像素角标 -->
        <div class="auth-corner-tl"></div>
        <div class="auth-corner-tr"></div>
        <div class="auth-corner-bl"></div>
        <div class="auth-corner-br"></div>
      </div>
    </div>`;
}

function skipAuth() {
  document.getElementById('auth-gate').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  App.init();
}

async function handleAuth(e, mode) {
  e.preventDefault();
  const btn = document.getElementById('auth-submit');
  const errEl = document.getElementById('auth-error');
  errEl.style.display = 'none';
  btn.disabled = true;
  btn.textContent = mode === 'login' ? '登录中…' : '注册中…';

  const username = document.getElementById('auth-username').value.trim();
  const password = document.getElementById('auth-password').value;

  if (!username || !password) {
    showAuthError('请填写用户名和密码');
    btn.disabled = false;
    btn.textContent = mode === 'login' ? '登 录' : '注 册';
    return;
  }

  try {
    const isRegister = mode === 'register';
    const r = await api.auth(isRegister ? 'register' : 'login', username, password);
    if (r.ok && r.data) {
      Auth.setToken(r.data.token);
      Auth.setUser({ id: r.data.user_id, username });
      showAppAfterAuth();
    } else if (r.detail) {
      showAuthError(r.detail);
    } else {
      showAuthError('操作失败，请重试');
    }
  } catch (e) {
    showAuthError(e.message || '网络错误，请检查后端是否运行');
  }
  btn.disabled = false;
  btn.textContent = mode === 'login' ? '登 录' : '注 册';
}

function showAuthError(msg) {
  const el = document.getElementById('auth-error');
  el.textContent = msg;
  el.style.display = 'block';
}

async function showAppAfterAuth() {
  document.getElementById('auth-gate').style.display = 'none';
  document.getElementById('app').style.display = 'flex';
  await App.init();
}

function showAuthGate() {
  document.getElementById('auth-gate').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
  renderAuthPage('login');
}

function doLogout() {
  Auth.clear();
  document.getElementById('auth-gate').style.display = 'flex';
  document.getElementById('app').style.display = 'none';
  renderAuthPage('login');
  App.state = {
    initialized: false,
    currentDay: 0,
    hometown: {},
    profile: {},
    postcards: [],
    letters: [],
    memories: [],
    pastSelfProfile: {},
  };
}
