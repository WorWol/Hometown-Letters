/* 明信片相册墙。 */

let _postcardQuery = '';

function _filteredPostcards(query) {
  const normalized = String(query || '').trim().toLowerCase();
  const all = App.state.postcards || [];
  return normalized
    ? all.filter(pc => `${pc.place || ''} ${pc.mood || ''} ${(pc.tags || pc.keywords || []).join(' ')} ${pc.title || ''} ${pc.body || ''}`.toLowerCase().includes(normalized))
    : all;
}

function _postcardResultsHtml(filtered, query) {
  const normalized = String(query || '').trim();
  return filtered.length ? `<div class="postcard-wall">${filtered.map((pc, index) => `
      <button class="album-card" onclick="App.showPostcardDetail(window._postcardWall[${index}])">
        <span class="album-image">${App._imgHtml(pc, { small: true })}</span>
        <span class="album-copy"><small>${App._e(pc.place || '沿途')}${pc.mood ? ` · ${App._e(pc.mood)}` : ''}</small><strong>${App._e(pc.title || '无题明信片')}</strong><em>${pc.createdAt ? new Date(pc.createdAt).toLocaleDateString('zh-CN') : ''}</em></span>
      </button>`).join('')}</div>` : `
      <div class="visual-empty large-empty paper-panel"><img src="assets/workbench/empty-mailbox-card.webp" alt="空白相册桌面"><div><h3>${normalized ? '没有找到这张记忆' : '相册墙还是空的'}</h3><p>${normalized ? '换一个地点或情绪试试。' : '寄出一封信，明信片会沿着时间回来。'}</p>${normalized ? '' : '<button class="btn btn-pri" onclick="App.navigate(\'write_letter\')">去写信</button>'}</div></div>`;
}

function filterPostcards(value) {
  _postcardQuery = String(value || '');
  const filtered = _filteredPostcards(_postcardQuery);
  window._postcardWall = filtered;
  const count = document.getElementById('pc-result-count');
  const results = document.getElementById('pc-results');
  if (count) count.textContent = `${filtered.length} 张沿途画面`;
  if (results) results.innerHTML = _postcardResultsHtml(filtered, _postcardQuery);
}

function renderPostcards() {
  const el = document.getElementById('page-postcards');
  if (!el) return;
  const activeInput = document.getElementById('pc-filter');
  if (activeInput) _postcardQuery = activeInput.value;
  const filtered = _filteredPostcards(_postcardQuery);
  window._postcardWall = filtered;
  el.innerHTML = `
    <section class="album-toolbar paper-panel">
      <div><span class="section-kicker">YOUR POSTCARD ALBUM</span><h2 id="pc-result-count">${filtered.length} 张沿途画面</h2><p>按地点、标签或情绪翻找一张旧照片。</p></div>
      <label class="search-field"><span>搜索明信片</span><input class="inp" id="pc-filter" placeholder="地点 / 标签 / 情绪" value="${App._e(_postcardQuery)}" oninput="filterPostcards(this.value)" autocomplete="off"></label>
    </section>
    <div id="pc-results">${_postcardResultsHtml(filtered, _postcardQuery)}</div>`;
}
