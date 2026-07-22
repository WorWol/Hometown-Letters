/* 登录 / 注册。 */

function renderAuthPage(mode = 'login') {
  const el = document.getElementById('page-auth');
  if (!el) return;
  const isLogin = mode === 'login';
  el.innerHTML = `
    <div class="auth-workbench">
      <section class="auth-scene" aria-label="暖灯下的故乡邮箱">
        <div class="auth-scene-copy">
          <span>HOMETOWN LETTERS</span>
          <h1>总有一封信<br>会沿着旧路回来</h1>
          <p>把今天写给过去，也让故乡替你保存那些没有说完的话。</p>
        </div>
      </section>
      <section class="auth-paper">
        <div class="auth-seal" aria-hidden="true">乡</div>
        <div class="auth-heading">
          <span class="section-kicker">A LETTER TO THE PAST</span>
          <h2>故乡来信</h2>
          <p>${isLogin ? '欢迎回到这张熟悉的书桌。' : '从一封写给过去的信开始。'}</p>
        </div>
        <div class="auth-tabs" role="tablist" aria-label="账户方式">
          <button class="auth-tab ${isLogin ? 'active' : ''}" role="tab" aria-selected="${isLogin}" onclick="renderAuthPage('login')">登录</button>
          <button class="auth-tab ${!isLogin ? 'active' : ''}" role="tab" aria-selected="${!isLogin}" onclick="renderAuthPage('register')">注册</button>
        </div>
        <form class="auth-form" onsubmit="handleAuth(event, '${mode}')">
          <label class="auth-field">你的名字
            <input type="text" id="auth-username" class="inp" placeholder="写下用户名" required minlength="2" maxlength="32" autocomplete="username">
          </label>
          <label class="auth-field">信箱暗号
            <input type="password" id="auth-password" class="inp" placeholder="至少 4 个字符" required minlength="4" autocomplete="${isLogin ? 'current-password' : 'new-password'}">
          </label>
          <div class="auth-err" id="auth-error" role="alert" hidden></div>
          <button type="submit" class="auth-submit" id="auth-submit">${isLogin ? '打开我的信箱' : '寄出第一封信'}</button>
        </form>
        <button class="auth-skip" type="button" onclick="skipAuth()">先看看这间温暖的房间 →</button>
      </section>
    </div>`;
}

function _setAppVisible(visible) {
  document.getElementById('auth-gate').style.display = visible ? 'none' : 'flex';
  document.getElementById('app').style.display = visible ? 'grid' : 'none';
  if (visible) requestAnimationFrame(() => document.querySelector('.room-backdrop')?.classList.add('loaded'));
}

function skipAuth() {
  _setAppVisible(true);
  App.init();
}

async function handleAuth(event, mode) {
  event.preventDefault();
  const button = document.getElementById('auth-submit');
  const username = document.getElementById('auth-username').value.trim();
  const password = document.getElementById('auth-password').value;
  const original = mode === 'login' ? '打开我的信箱' : '寄出第一封信';
  document.getElementById('auth-error').hidden = true;
  button.disabled = true;
  button.textContent = mode === 'login' ? '正在开锁…' : '正在登记…';
  try {
    const response = await api.auth(mode === 'register' ? 'register' : 'login', username, password);
    if (!response.ok || !response.data) throw new Error(response.detail || response.error || '操作失败，请重试');
    Auth.setToken(response.data.token);
    Auth.setUser({ id: response.data.user_id, username });
    await showAppAfterAuth();
  } catch (error) {
    showAuthError(error.message || '网络错误，请检查后端是否运行');
  } finally {
    button.disabled = false;
    button.textContent = original;
  }
}

function showAuthError(message) {
  const el = document.getElementById('auth-error');
  if (!el) return;
  el.textContent = message;
  el.hidden = false;
}

async function showAppAfterAuth() {
  _setAppVisible(true);
  await App.init();
}

function showAuthGate() {
  _setAppVisible(false);
  renderAuthPage('login');
}

function doLogout() {
  Auth.clear();
  App.state = {
    initialized: false, currentDay: 0, hometown: {}, profile: {}, postcards: [], letters: [], memories: [], pastSelfProfile: {}, likedItems: [],
  };
  showAuthGate();
}
