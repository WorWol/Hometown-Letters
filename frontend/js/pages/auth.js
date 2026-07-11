/* ===== 登录/注册页面 ===== */

function renderAuthPage(mode) {
  const el = document.getElementById('page-auth');
  const isLogin = mode === 'login';
  el.innerHTML = `
    <div class="auth-container">
      <div class="auth-card">
        <div class="auth-header">
          <h1>故乡来信</h1>
          <p>给过去的自己写一封信</p>
        </div>
        <div class="auth-tabs">
          <button class="auth-tab ${isLogin ? 'active' : ''}" onclick="renderAuthPage('login')">登录</button>
          <button class="auth-tab ${!isLogin ? 'active' : ''}" onclick="renderAuthPage('register')">注册</button>
        </div>
        <form class="auth-form" onsubmit="handleAuth(event, '${mode}')">
          <div class="auth-field">
            <label>用户名</label>
            <input type="text" id="auth-username" class="inp" placeholder="请输入用户名" required minlength="2" maxlength="32">
          </div>
          <div class="auth-field">
            <label>密码</label>
            <input type="password" id="auth-password" class="inp" placeholder="请输入密码" required minlength="4">
          </div>
          <div class="auth-err" id="auth-error" style="display:none;"></div>
          <button type="submit" class="btn btn-pri auth-submit" id="auth-submit">
            ${isLogin ? '登 录' : '注 册'}
          </button>
        </form>
      </div>
    </div>`;
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
    } else if (r.ok === false && r.detail) {
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
