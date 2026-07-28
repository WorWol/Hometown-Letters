/* 应用核心：状态、通用媒体处理与轻量工具。 */

const App = {
  state: {
    initialized: false,
    currentDay: 0,
    hometown: {},
    profile: {},
    postcards: [],
    letters: [],
    memories: [],
    pastSelfProfile: {},
    likedItems: [],
    imageStyle: null,
    onboardingVersion: null,
  },

  currentPage: 'game',

  async init() {
    try {
      const response = await api.getState();
      if (response.ok && response.data) this.applyState(response.data);
    } catch (error) {
      if ((error?.status === 401 || error?.message === '未登录') && Auth.isLoggedIn()) {
        if (typeof showAuthGate === 'function') showAuthGate();
        return;
      }
      if (Auth.isLoggedIn()) console.warn('[app] 无法获取状态', error);
    }
    this.navigate(this.currentPage);
    window.Onboarding?.maybeStart();
  },

  getMediaUrl(valueOrRecord) {
    const raw = typeof valueOrRecord === 'string'
      ? valueOrRecord
      : valueOrRecord?.imageUrl ?? valueOrRecord?.image_url ?? valueOrRecord?.imagePath ?? valueOrRecord?.image_path;
    if (raw === null || raw === undefined) return '';
    const value = String(raw).trim();
    if (!value) return '';
    if (/^(?:https?:|data:|blob:)/i.test(value) || value.startsWith('/') || value.startsWith('./') || value.startsWith('../') || value.startsWith('assets/')) {
      return value;
    }
    return `/api/image/${encodeURIComponent(value)}`;
  },

  normalizePostcard(postcard) {
    if (!postcard || typeof postcard !== 'object') return postcard;
    const createdAt = postcard.createdAt ?? postcard.created_at ?? postcard.timestamp ?? '';
    return {
      ...postcard,
      createdAt,
      generationPlace: postcard.generationPlace ?? postcard.generation_place ?? postcard.place ?? '',
      imageUrl: this.getMediaUrl(postcard),
      usedFallback: postcard.usedFallback ?? postcard.used_fallback ?? false,
      keywords: postcard.keywords ?? postcard.tags ?? [],
    };
  },

  normalizeCommunityItem(item) {
    if (!item || typeof item !== 'object') return item;
    return { ...item, postcard: this.normalizePostcard(item.postcard) };
  },

  normalizeMail(mail) {
    if (!mail || typeof mail !== 'object') return mail;
    return {
      ...mail,
      attachedPostcard: this.normalizePostcard(mail.attachedPostcard ?? mail.attached_postcard),
      attachedLetter: mail.attachedLetter ?? mail.attached_letter,
    };
  },

  applyState(data = {}) {
    const postcards = Array.isArray(data.postcards) ? data.postcards.map(item => this.normalizePostcard(item)) : (this.state.postcards || []);
    const likedRaw = data.likedItems ?? data.liked_items ?? this.state.likedItems ?? [];
    this.state = {
      ...this.state,
      ...data,
      currentDay: data.current_day ?? data.currentDay ?? this.state.currentDay ?? 0,
      pastSelfProfile: data.past_self_profile ?? data.pastSelfProfile ?? this.state.pastSelfProfile ?? {},
      likedItems: Array.isArray(likedRaw) ? likedRaw.map(item => this.normalizeCommunityItem(item)) : [],
      imageStyle: data.imageStyle ?? data.image_style ?? this.state.imageStyle ?? null,
      onboardingVersion: data.onboardingVersion ?? data.onboarding_version ?? null,
      postcards,
      letters: Array.isArray(data.letters) ? data.letters : (this.state.letters || []),
      memories: Array.isArray(data.memories) ? data.memories : (this.state.memories || []),
      initialized: true,
    };
    this.syncShell?.();
    return this.state;
  },

  async refreshState() {
    const response = await api.getState();
    if (response.ok && response.data) this.applyState(response.data);
    return response;
  },

  showToast(message, duration = 2500) {
    const container = document.getElementById('toast-container');
    if (!container) return;
    const toast = document.createElement('div');
    toast.className = 'toast';
    toast.textContent = message;
    container.appendChild(toast);
    setTimeout(() => {
      toast.classList.add('leaving');
      setTimeout(() => toast.remove(), 260);
    }, duration);
  },

  friendlyError(error, fallback = '操作失败，请稍后重试') {
    const status = Number(error?.status || 0);
    const raw = typeof error === 'string'
      ? error
      : String(error?.detail || error?.error || error?.message || '').trim();
    if (status === 401 || raw === '未登录' || raw.includes('认证令牌')) return '登录已失效，请重新登录';
    if (status === 403 || raw.includes('无权')) return '你没有权限执行此操作';
    if (raw.includes('不能给自己发信')) return '不能给自己发送信件';
    if (raw.includes('收件人不存在')) return '没有找到收件人，请检查用户名';
    if (status === 404 || raw.includes('不存在')) return '没有找到相关内容';
    if (status === 409 || raw.includes('用户名已存在')) return raw || '内容发生冲突，请检查后重试';
    if (status === 413 || raw.includes('不能超过')) return raw || '文件过大，请选择较小的文件';
    if (status === 415 || raw.includes('仅支持') || raw.includes('不支持')) return raw || '文件格式不受支持';
    if (status === 422) return raw && !raw.startsWith('HTTP ') ? raw : '输入内容有误，请检查后重试';
    if (status === 429 || raw.includes('过于频繁') || raw.includes('最多生成')) return raw || '操作过于频繁，请稍后重试';
    if (status >= 500 || /^HTTP \d+/i.test(raw) || /^[A-Za-z]+(?:Error|Exception):/.test(raw)) return fallback;
    if (raw === '网络错误' || raw.includes('Failed to fetch') || raw.includes('NetworkError')) return '网络连接失败，请稍后重试';
    return raw || fallback;
  },

  relativeTime(timestamp) {
    if (!timestamp) return '';
    const date = new Date(timestamp);
    if (Number.isNaN(date.getTime())) return '';
    const elapsed = Math.max(0, Date.now() - date.getTime());
    if (elapsed < 60000) return '刚刚';
    if (elapsed < 3600000) return `${Math.max(1, Math.floor(elapsed / 60000))} 分钟前`;
    if (elapsed < 86400000) return `${Math.floor(elapsed / 3600000)} 小时前`;
    if (elapsed < 604800000) return `${Math.floor(elapsed / 86400000)} 天前`;
    return date.toLocaleDateString('zh-CN');
  },

  _imgGradient(place, mood) {
    if (mood?.includes('平静') || mood?.includes('宁静')) return 'linear-gradient(145deg,#6f9188,#adc0a5 58%,#dfc999)';
    if (mood?.includes('怀念')) return 'linear-gradient(145deg,#8c674e,#c49e72 52%,#e2c99f)';
    if (mood?.includes('温暖')) return 'linear-gradient(145deg,#b87355,#d8aa78 52%,#efd7a8)';
    const seed = String(place || '').length % 3;
    return [
      'linear-gradient(145deg,#748a65,#a8b489 48%,#d8bd82)',
      'linear-gradient(145deg,#607f83,#91aaa1 48%,#d7c292)',
      'linear-gradient(145deg,#7d6655,#b99a77 48%,#ddc39a)',
    ][seed];
  },

  handleMediaLoad(image) {
    image?.closest('.media-frame')?.classList.add('is-loaded');
  },

  handleMediaError(image) {
    const frame = image?.closest('.media-frame');
    if (frame) frame.classList.add('is-fallback');
    if (image) image.hidden = true;
  },

  _imgHtml(postcard = {}, options = {}) {
    const pc = this.normalizePostcard(postcard) || {};
    const imageUrl = pc.imageUrl;
    const place = this._e(pc.place || '沿途');
    const mood = this._e(pc.mood || '');
    const compact = options.small ? ' compact' : '';
    const state = imageUrl ? ' has-image' : ' is-fallback';
    return `<div class="media-frame${compact}${state}" style="--media-fallback:${this._imgGradient(pc.place, pc.mood)}">
      ${imageUrl ? `<img src="${this._e(imageUrl)}" alt="${place}的明信片画面" loading="lazy" draggable="false" data-no-visual-search="true" onload="App.handleMediaLoad(this)" onerror="App.handleMediaError(this)">` : ''}
      <div class="media-fallback" aria-hidden="${imageUrl ? 'true' : 'false'}">
        <span class="media-fallback-mark">□</span><strong>图片暂不可用</strong><small>${place}${mood ? ` · ${mood}` : ''}</small>
      </div>
    </div>`;
  },

  _backgroundMediaHtml(postcard = {}, options = {}) {
    const pc = this.normalizePostcard(postcard) || {};
    const imageUrl = pc.imageUrl;
    const place = this._e(pc.place || '沿途');
    const mood = this._e(pc.mood || '');
    const compact = options.small ? ' compact' : '';
    const state = imageUrl ? ' has-image' : ' is-fallback';
    const fallback = this._imgGradient(pc.place, pc.mood);
    const background = imageUrl
      ? `background-image:url(${this._e(JSON.stringify(imageUrl))}),${fallback}`
      : `background-image:${fallback}`;
    return `<div class="media-frame background-media${compact}${state}" style="--media-fallback:${fallback};${background}">
      ${imageUrl ? `<img class="media-probe" src="${this._e(imageUrl)}" alt="" aria-hidden="true" loading="lazy" draggable="false" data-no-visual-search="true" onload="App.handleMediaLoad(this)" onerror="App.handleMediaError(this)">` : ''}
      <div class="media-fallback" aria-hidden="${imageUrl ? 'true' : 'false'}">
        <span class="media-fallback-mark">□</span><strong>图片暂不可用</strong><small>${place}${mood ? ` · ${mood}` : ''}</small>
      </div>
    </div>`;
  },

  _e(value) {
    if (value === null || value === undefined) return '';
    return String(value).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  },

  _js(value) {
    return JSON.stringify(String(value ?? ''))
      .replace(/</g, '\\u003c').replace(/>/g, '\\u003e').replace(/&/g, '\\u0026')
      .replace(/'/g, '\\u0027').replace(/"/g, '&quot;');
  },
};

function enlargePostcardImage(source) {
  if (!source) return;
  const overlay = document.createElement('div');
  overlay.className = 'image-lightbox';
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.setAttribute('aria-label', '明信片图片预览');
  overlay.tabIndex = -1;

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'lightbox-close';
  closeButton.setAttribute('aria-label', '关闭图片预览');
  closeButton.textContent = '×';

  const clone = source.cloneNode(true);
  clone.removeAttribute('onclick');
  clone.onclick = null;
  clone.removeAttribute('aria-label');
  clone.setAttribute('aria-hidden', 'true');
  clone.tabIndex = -1;
  clone.classList.add('lightbox-media');
  overlay.appendChild(closeButton);
  overlay.appendChild(clone);

  const close = () => {
    document.removeEventListener('keydown', onKeydown);
    overlay.remove();
  };
  const onKeydown = (event) => {
    if (event.key === 'Escape') close();
  };

  overlay.addEventListener('click', close);
  document.addEventListener('keydown', onKeydown);
  document.body.appendChild(overlay);
  closeButton.focus({ preventScroll: true });
}
