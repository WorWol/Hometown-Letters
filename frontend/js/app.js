/* ===== 应用核心：路由 + 状态 + UI ===== */

const App = {
  _authMode: 'demo', // 'demo' | 'v2'

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
    if (this._authMode === 'v2') {
      try {
        const r = await api.v2GetState();
        if (r.ok && r.data && r.data.hometown?.hometownName) {
          this.state = { ...this.state, ...r.data };
          this.state.initialized = true;
          this.state.currentDay = r.data.current_day || 0;
        } else {
          this._loadDemoData();
        }
      } catch (_) {
        console.log('v2 backend unavailable');
        this._loadDemoData();
      }
    } else {
      // demo mode: try old API, fall back to demo data
      try {
        const r = await api.getState();
        if (r.ok && r.data && r.data.hometown?.hometownName) {
          this.state = { ...this.state, ...r.data };
          this.state.initialized = true;
          this.state.currentDay = r.data.current_day || 0;
        } else {
          this._loadDemoData();
        }
      } catch (_) {
        console.log('backend unavailable');
        this._loadDemoData();
      }
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

  _loadDemoData() {
    this.state = {
      initialized: true,
      currentDay: 5,
      hometown: { province:'湖南', city:'郴州', county:'资兴', hometownName:'资兴' },
      profile: {},
      postcards: [
        { id:'1', title:'夏日午后', place:'秀流公园', body:'阳光从梧桐叶缝里漏下来，地上是碎金一样的光斑。风把树叶吹得沙沙响，远处的知了声一浪接一浪。', imageUrl:null, createdAt:'2026-07-01T10:00:00Z', mood:'平静', tags:['夏天','公园'], poem:'那时以为夏天永远不会结束。' },
        { id:'2', title:'东江湖边', place:'东江湖', body:'雾漫东江，小船在晨雾里若隐若现。站在栈道上，闻到水草和晨露的味道。', imageUrl:null, createdAt:'2026-07-02T06:30:00Z', mood:'宁静', tags:['水边','清晨'], poem:'雾气散去后，山还是那座山。' },
        { id:'3', title:'老槐树下', place:'老街', body:'村口的老槐树还在，树荫下有几个老人在下棋。走过去的时候，闻到了熟悉的烟火味。', imageUrl:null, createdAt:'2026-07-03T15:00:00Z', mood:'怀念', tags:['老街','树'], poem:'有些地方，连风都是旧的。' },
      ],
      letters: [
        { text:'今天天气不错，我想去走走看看。', place:'资兴', mood:'平静', timestamp:'2026-07-01T09:00:00Z' },
        { text:'想再去一次东江湖。', place:'东江湖', mood:'宁静', timestamp:'2026-07-02T06:00:00Z' },
      ],
      memories: [
        { text:'小时候喜欢躺在竹席上听外婆讲故事', tags:['家','童年'], timestamp:'2026-07-04T20:00:00Z', analysisStatus:'completed', summary:'外婆的故事是夏夜里最好的催眠曲。' },
        { text:'学校后门的那棵桂花树，秋天的时候整个走廊都是甜的', tags:['学校','秋天'], timestamp:'2026-07-05T14:00:00Z', analysisStatus:'completed', summary:'那个味道，后来再也没有闻到过。' },
        { text:'第一次学会骑自行车是在晒谷场上', tags:['童年','技能'], timestamp:'2026-07-06T16:00:00Z', analysisStatus:'completed', summary:'摔了好多次，但学会的那天觉得自己很了不起。' },
      ],
      pastSelfProfile: {
        summary:'是个会一个人发呆很久的小孩，喜欢风和水面的光。',
        latent_place_affinities:[{name:'秀流公园'},{name:'东江湖'},{name:'老街'},{name:'学校'},{name:'晒谷场'},{name:'河边'}],
        sensory_biases:[{name:'桂花香'},{name:'蝉鸣'},{name:'竹席凉'},{name:'水草味'},{name:'树影光斑'},{name:'烟火味'}],
        identity_signals:[{name:'不爱说话的孩子'},{name:'会把很小的事情记很久'},{name:'总会在热闹结束后多停一下'},{name:'会被风和空气里的变化悄悄打动'}],
        recent_memory_signals:[{name:'外婆的故事'},{name:'桂花香'},{name:'晒谷场'}],
      },
    };
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
          <div class="fr">
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
