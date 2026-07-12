/* ===== 应用核心：路由 + 状态 + UI ===== */

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
  },

  currentPage: 'game',

  async init() {
    try {
      const r = await api.getState();
      if (r.ok && r.data) {
        this.state = { ...this.state, ...r.data };
        this.state.initialized = true;
        this.state.currentDay = r.data.current_day || 0;
      }
    } catch (_) {
      console.log('无法获取状态，请先登录');
    }
    this.navigate(this.currentPage);
  },

  navigate(page) {
    document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
    const t = document.getElementById(`page-${page}`);
    if (t) t.classList.add('active');
    document.querySelectorAll('.nav-btn').forEach(b => b.classList.toggle('active', b.dataset.page === page));
    this.currentPage = page;
    const fn = `render${page.split('_').map(s=>s[0].toUpperCase()+s.slice(1)).join('')}`;
    if (typeof window[fn] === 'function') window[fn]();
  },

  showToast(msg, dur = 2500) {
    const c = document.getElementById('toast-container');
    const t = document.createElement('div');
    t.className = 'toast';
    t.textContent = msg;
    c.appendChild(t);
    setTimeout(() => { t.style.opacity = '0'; t.style.transition = 'opacity 0.4s'; setTimeout(()=>t.remove(),400); }, dur);
  },

  showPostcardDetail(pc) {
    const e = document.querySelector('.modal');
    if (e) e.remove();
    const o = document.createElement('div');
    o.className = 'modal';
    o.onclick = e => { if (e.target === o) o.remove(); };
    const poem = pc.poem || '';
    const tags = pc.keywords || pc.tags || [];
    const imgHtml = this._imgHtml(pc);

    o.innerHTML = `
      <div class="modal-pnl">
        <div class="modal-hd">
          <h3>${this._e(pc.title||'无题明信片')}</h3>
          <button class="modal-cl" onclick="this.closest('.modal').remove()">×</button>
        </div>
        <div class="modal-meta">
          ${this._e(pc.place||'')}${pc.place&&pc.mood?' · ':''}${this._e(pc.mood||'')}
          ${pc.createdAt?' · '+new Date(pc.createdAt).toLocaleDateString('zh-CN'):''}
        </div>
        <div class="modal-pc">
          <div class="fr" onclick="event.stopPropagation();enlargePostcardImage(this.querySelector('.iw'))">
            <img class="ov" src="assets/postcard_frame.png" alt="">
            <div class="iw">${imgHtml}</div>
          </div>
        </div>
        <div class="modal-bd">${this._e(pc.body||'')}</div>
        ${poem ? `<div class="modal-poem">${this._e(poem)}</div>` : ''}
        <div class="modal-tags">${tags.map(t=>`<span class="tag">${this._e(String(t))}</span>`).join('')}</div>
        ${pc.letterText?`<div class="modal-poem" style="border-top:none;font-style:normal;font-size:13px;color:var(--dk-muted);">来信：${this._e(pc.letterText.slice(0,80))}${pc.letterText.length>80?'…':''}</div>`:''}
        <div class="modal-ft">
          <button class="btn btn-sec" onclick="this.closest('.modal').remove()">关闭</button>
        </div>
      </div>`;
    document.body.appendChild(o);
  },

  /* 根据地点/情绪生成场景渐变 "照片" */
  _imgGradient(place, mood) {
    const scenes = {
      '秀流公园':'linear-gradient(145deg,#6B9E6B 0%,#8CB87C 25%,#C9B88A 60%,#D4A76A 100%)',
      '东江湖':'linear-gradient(145deg,#6A9AB5 0%,#8BB8C9 30%,#A8C8D8 55%,#A8C0A8 100%)',
      '老街':'linear-gradient(145deg,#A08060 0%,#C4A882 30%,#D8C4A8 60%,#C8A880 100%)',
      '学校':'linear-gradient(145deg,#7DA87D 0%,#A8C8A0 30%,#C8D8B8 60%,#D0C090 100%)',
      '晒谷场':'linear-gradient(145deg,#C8A860 0%,#D8C080 30%,#E0D098 60%,#D0B870 100%)',
      '资兴':'linear-gradient(145deg,#7BA87B 0%,#A0C0A0 35%,#C0C8A8 65%,#D0C098 100%)',
      default:'linear-gradient(145deg,#B8C8B0 0%,#C8D0BC 35%,#D0C8B0 65%,#C0B0A0 100%)',
    };
    if (place && scenes[place]) return scenes[place];
    if (mood) {
      if (mood.includes('平静')||mood.includes('宁静')) return 'linear-gradient(145deg,#7AA8A0 0%,#90B8B0 35%,#B0C8B8 65%,#C0D0B8 100%)';
      if (mood.includes('怀念')) return 'linear-gradient(145deg,#A0805E 0%,#C0A880 35%,#D0B898 65%,#C8A880 100%)';
      if (mood.includes('温暖')) return 'linear-gradient(145deg,#C8906E 0%,#D0B090 40%,#D8C0A0 70%,#E0D0B0 100%)';
    }
    return scenes.default;
  },

  /* 渲染明信片图片区域（真实图或渐变占位） */
  _imgHtml(pc, opts = {}) {
    const { small } = opts;
    const img = pc.imageUrl;
    if (img) {
      const g = this._imgGradient(pc.place, pc.mood);
      return `<div style="width:100%;height:100%;background:${g};border-radius:inherit;">
          <img src="${this._e(img)}" alt="" loading="eager"
            onerror="this.style.display='none'"
            style="width:100%;height:100%;object-fit:cover;display:block;">
        </div>`;
    }
    const g = this._imgGradient(pc.place, pc.mood);
    const place = this._e(pc.place || '');
    const mood = this._e(pc.mood || '');
    const label = small ? '' : `<div class="ph-lbl">${place}${mood?' · '+mood:''}</div>`;
    return `<div class="ph-img" style="background:${g}">${label}</div>`;
  },

  _e(s) { if(!s)return''; return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); },
};

/* ================ 明信片图片点击放大 ================ */

function enlargePostcardImage(iwEl) {
  if (!iwEl) return;

  // 创建全屏遮罩
  const overlay = document.createElement('div');
  overlay.className = 'env-overlay';

  // 克隆图片容器
  const clone = iwEl.cloneNode(true);
  clone.className = 'env-img-large';

  // 如果有 img 标签，修复其样式以显示原图
  const img = clone.querySelector('img');
  if (img) {
    img.style.width = 'auto';
    img.style.height = 'auto';
    img.style.maxWidth = '90vw';
    img.style.maxHeight = '85vh';
    img.style.objectFit = 'contain';
    img.style.display = 'block';
    img.onerror = function() { this.style.display = 'none'; };
  }

  overlay.appendChild(clone);

  // 点击遮罩关闭
  overlay.addEventListener('click', function() {
    overlay.remove();
  });

  document.body.appendChild(overlay);
};
