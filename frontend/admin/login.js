(() => {
  const form = document.getElementById('developer-login-form');
  const username = document.getElementById('developer-username');
  const password = document.getElementById('developer-password');
  const error = document.getElementById('login-error');
  const button = form.querySelector('button');
  username.value = localStorage.getItem('hometown_developer_username') || '';
  if (username.value) password.focus();
  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    error.textContent = '';
    button.disabled = true;
    button.querySelector('span').textContent = '正在验证…';
    try {
      const response = await fetch('/api/auth/login', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({username: username.value.trim(), password: password.value})});
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.detail || '开发者登录失败');
      if (!payload.data?.is_developer) throw new Error('该账号不是开发者账号');
      localStorage.setItem('hometown_developer_token', payload.data.token);
      localStorage.setItem('hometown_developer_username', username.value.trim());
      window.location.replace('/admin.html');
    } catch (loginError) {
      error.textContent = loginError.message;
      button.disabled = false;
      button.querySelector('span').textContent = '登录工作区';
    }
  });
})();
