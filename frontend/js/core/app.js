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

  navigate(page) {
    document.querySelectorAll('#app .page').forEach(node => node.classList.remove('active'));
    document.getElementById(`page-${page}`)?.classList.add('active');
    this.currentPage = page;
    const fn = `render${page.split('_').map(part => part[0].toUpperCase() + part.slice(1)).join('')}`;
    if (typeof window[fn] === 'function') window[fn]();
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
        <span class="media-fallback-mark">□</span><strong>画面暂缺</strong><small>${place}${mood ? ` · ${mood}` : ''}</small>
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
        <span class="media-fallback-mark">□</span><strong>画面暂缺</strong><small>${place}${mood ? ` · ${mood}` : ''}</small>
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
  overlay.setAttribute('aria-label', '明信片放大预览');
  overlay.tabIndex = -1;

  const closeButton = document.createElement('button');
  closeButton.type = 'button';
  closeButton.className = 'lightbox-close';
  closeButton.setAttribute('aria-label', '缩小图片');
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
