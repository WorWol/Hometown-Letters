/* ===== API 客户端 ===== */

const API_BASE = window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost' ? '' : 'http://127.0.0.1:8787';

const api = {
  async _fetch(path, options = {}) {
    const url = `${API_BASE}${path}`;
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 180000);
    const config = {
      headers: { 'Content-Type': 'application/json' },
      signal: controller.signal,
      ...options,
    };
    try {
      const resp = await fetch(url, config);
      clearTimeout(timer);
      if (!resp.ok) {
        const text = await resp.text();
        throw new Error(`HTTP ${resp.status}: ${text.slice(0, 100)}`);
      }
      return resp.json();
    } catch (e) {
      clearTimeout(timer);
      if (e.name === 'AbortError') throw new Error('请求超时，请稍后重试');
      throw e;
    }
  },

  _fetchAuth(path, options = {}) {
    const token = Auth.getToken();
    if (!token) throw new Error('未登录');

    const headers = {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`,
      ...options.headers,
    };
    return this._fetch(path, { ...options, headers });
  },

  // ── 认证 ──

  async auth(action, username, password) {
    const r = await fetch(`${API_BASE}/api/auth/${action}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password }),
    });
    return r.json();
  },

  async getMe() {
    return this._fetchAuth('/api/auth/me');
  },

  // ── 游戏 API（需要 token）──

  async getState() {
    return this._fetchAuth('/api/state');
  },

  async initHometown(data) {
    return this._fetchAuth('/api/hometown/init', {
      method: 'POST',
      body: JSON.stringify(data),
    });
  },

  async sendLetter(text, placeHint = '', moodHint = '') {
    return this._fetchAuth('/api/letter/send', {
      method: 'POST',
      body: JSON.stringify({ text, place_hint: placeHint, mood_hint: moodHint }),
    });
  },

  async saveMemory(text, tags = [], placeHint = '') {
    return this._fetchAuth('/api/memory/save', {
      method: 'POST',
      body: JSON.stringify({ text, tags, place_hint: placeHint }),
    });
  },

  async getPostcards() {
    return this._fetchAuth('/api/postcards');
  },

  async getLandmarks() {
    return this._fetchAuth('/api/landmarks');
  },
};
