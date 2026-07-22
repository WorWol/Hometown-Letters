/* ===== API 客户端 ===== */

// Production is served by the same FastAPI process as the frontend. Keep API
// calls same-origin so a public browser never tries to call its own 127.0.0.1.
// The only cross-origin case is the separate local static server used during
// frontend work (for example localhost:5500 -> localhost:8787).
const isLocalFrontendServer = (
  (window.location.hostname === '127.0.0.1' || window.location.hostname === 'localhost') &&
  window.location.port !== '' &&
  window.location.port !== '8787'
);
const API_BASE = isLocalFrontendServer
  ? `${window.location.protocol}//${window.location.hostname}:8787`
  : '';

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
        const error = new Error(`HTTP ${resp.status}: ${text.slice(0, 100)}`);
        error.status = resp.status;
        error.responseText = text;
        if (resp.status === 401 && window.Auth && typeof window.Auth.clear === 'function') {
          window.Auth.clear();
        }
        throw error;
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
    if (!token) {
      const error = new Error('未登录');
      error.status = 401;
      throw error;
    }

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

  // ── 社区信件 ──

  async getCommunityLetters(limit = 5) {
    return this._fetchAuth(`/api/community-letters?limit=${limit}`);
  },

  // ── 用户查找 ──

  async lookupUsers(query) {
    return this._fetchAuth(`/api/users/lookup?q=${encodeURIComponent(query)}`);
  },

  // ── 邮件 ──

  async sendMail(recipientUsername, title, content, attachedPostcardId = null, attachedLetterId = null) {
    return this._fetchAuth('/api/mail/send', {
      method: 'POST',
      body: JSON.stringify({
        recipient_username: recipientUsername,
        title: title,
        content: content,
        attached_postcard_id: attachedPostcardId,
        attached_letter_id: attachedLetterId,
      }),
    });
  },

  async getInbox(page = 1, pageSize = 20) {
    return this._fetchAuth(`/api/mail/inbox?page=${page}&page_size=${pageSize}`);
  },

  async getOutbox(page = 1, pageSize = 20) {
    return this._fetchAuth(`/api/mail/outbox?page=${page}&page_size=${pageSize}`);
  },

  async getMailDetail(mailId) {
    return this._fetchAuth(`/api/mail/${mailId}`);
  },

  async markMailRead(mailId) {
    return this._fetchAuth(`/api/mail/${mailId}/read`, { method: 'PUT' });
  },

  async deleteMail(mailId) {
    return this._fetchAuth(`/api/mail/${mailId}`, { method: 'DELETE' });
  },

  // ── 社区发现 ──

  async getCommunityFeed(limit = 10) {
    return this._fetchAuth(`/api/community/feed?limit=${limit}`);
  },

  async likeCommunityLetter(letterId) {
    return this._fetchAuth(`/api/community/like/${letterId}`, { method: 'POST' });
  },

  async unlikeCommunityLetter(letterId) {
    return this._fetchAuth(`/api/community/like/${letterId}`, { method: 'DELETE' });
  },

};
