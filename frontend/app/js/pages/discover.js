/* ================================================================
   故乡来信 · 社区发现 (Discover)
   骨架屏先渲染，数据异步加载，点赞局部更新
   ================================================================ */

let _discoverItems = [];
let _discRequest = 0;

function renderDiscover() {
  const el = document.getElementById('page-discover');
  if (!el) return;
  // 骨架先出
  el.innerHTML = `
    <div class="discover-feed">
      <div class="panel-heading">
        <div>
          <span class="section-kicker">COMMUNITY FEED</span>
          <h2>远方的来信</h2>
        </div>
        <button class="text-button" onclick="renderDiscover()">↻ 换一批</button>
      </div>
      <p class="discover-desc">看看其他人写给过去的信。喜欢就点亮它，它会落在你的桌面上。</p>
      <div class="discover-grid" id="discover-list">
        ${Array.from({length:6}, () => `
          <div class="discover-card-skel">
            <div class="skel-bar w60"></div>
            <div class="skel-bar w80"></div>
            <div class="skel-bar w40"></div>
          </div>
        `).join('')}
      </div>
    </div>
  `;
  _loadDiscoverFeed(++_discRequest);
}

async function _loadDiscoverFeed(requestId = _discRequest) {
  const listEl = document.getElementById('discover-list');
  try {
    const r = await api.getCommunityFeed(12);
    if (requestId !== _discRequest) return;
    if (!r.ok || !r.data) { if (listEl) listEl.innerHTML = '<div class="visual-empty"><div><p>暂时没有远方的来信。</p></div></div>'; return; }
    _discoverItems = (r.data.items || []).map(item => App.normalizeCommunityItem(item));
    if (listEl) _renderDiscoverList(listEl);
  } catch (e) {
    if (requestId === _discRequest && listEl) listEl.innerHTML = '<div class="visual-empty"><div><p>网络不好，再试一次吧。</p><button class="btn btn-sec" onclick="renderDiscover()">再试一次</button></div></div>';
  } finally {
  }
}

function _renderDiscoverList(container) {
  const items = _discoverItems;
  if (!items.length) {
    container.innerHTML = '<div class="visual-empty"><div><p>暂时没有远方的来信。</p></div></div>';
    return;
  }

  const dateFmt = (ts) => {
    if (!ts) return '';
    const d = new Date(ts), now = new Date(), diff = now - d;
    if (diff < 86400000) return '今天';
    if (diff < 604800000) return `${Math.floor(diff / 86400000)}天前`;
    return d.toLocaleDateString('zh-CN');
  };

  // 先存引用，再渲染，确保 onclick 能取到
  window._discPC = {};
  items.forEach((item, i) => { if (item.postcard) window._discPC[i] = item.postcard; });

  container.innerHTML = items.map((item, i) => {
    const pc = item.postcard;
    const hasPc = !!(pc && (pc.imageUrl || pc.body));
    return `
      <div class="disc-card">
        ${hasPc ? `
        <button type="button" class="disc-card-img" aria-label="打开明信片详情" onclick="event.stopPropagation();App.showPostcardDetail(window._discPC[${i}])">
          ${App._imgHtml(pc, { small: true })}
        </button>` : ''}
        <div class="disc-card-bd">
          <div class="disc-card-top">
            <span class="disc-avatar">${(item.author?.username || '?')[0]}</span>
            <div class="disc-card-by">
              <strong>${App._e(item.author?.username || '远方来信')}</strong>
              <small>${App._e(item.author?.hometown || '')} · ${dateFmt(item.timestamp)}</small>
            </div>
          </div>
          <p class="disc-text">${App._e((item.text || '').slice(0, 120))}</p>
          <div class="disc-card-foot">
            <span class="disc-tags">
              ${item.place ? `<span class="tag">📍 ${App._e(item.place)}</span>` : ''}
              ${item.mood ? `<span class="tag">${App._e(item.mood)}</span>` : ''}
            </span>
            <button type="button" class="disc-like ${item.liked ? 'on' : ''}" id="disc-like-${i}"
              aria-label="${item.liked ? '取消收藏' : '收藏这封信'}" aria-pressed="${item.liked}"
              onclick="_toggleLike(${i})">${item.liked ? '♥' : '♡'}</button>
          </div>
        </div>
      </div>`;
  }).join('');
}

/* ── 点赞：只更新当前按钮，不重绘列表 ── */
async function _toggleLike(index) {
  const item = _discoverItems[index];
  if (!item) return;
  const btn = document.getElementById('disc-like-' + index);
  if (btn?.disabled) return;
  if (btn) btn.disabled = true;
  const letterId = String(item.id).replace('ltr-', '');
  try {
    if (item.liked) {
      const r = await api.unlikeCommunityLetter(letterId);
      if (r.ok) {
        item.liked = false;
        _updateLikeBtn(index, false);
        App.state.likedItems = (App.state.likedItems || []).filter(saved => saved.id !== item.id);
        App.showToast('已从桌面取下');
      }
    } else {
      const r = await api.likeCommunityLetter(letterId);
      if (r.ok) {
        item.liked = true;
        _updateLikeBtn(index, true);
        App.state.likedItems = [item, ...(App.state.likedItems || []).filter(saved => saved.id !== item.id)];
        App.showToast('已收藏到桌面 ✨');
      }
    }
  } catch (e) { App.showToast('操作失败', 2000); }
  if (btn) btn.disabled = false;
}

function _updateLikeBtn(index, liked) {
  const btn = document.getElementById('disc-like-' + index);
  if (btn) {
    btn.innerHTML = liked ? '♥' : '♡';
    btn.classList.toggle('on', liked);
    btn.setAttribute('aria-label', liked ? '取消收藏' : '收藏这封信');
    btn.setAttribute('aria-pressed', String(liked));
  }
}
