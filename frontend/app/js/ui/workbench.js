/* 全屏工作台壳层、导航和通用弹窗。页面渲染器位于 pages/。 */

const WORKBENCH_PAGE_META = {
  game: ['DESKTOP · 暖灯已亮', '桌上的来信', '查看旅程、明信片和最近记录。'],
  write_letter: ['WRITE · 寄往过去', '写一封信', '写下想说的话，投递后会生成明信片。'],
  postcards: ['ALBUM · 沿途风景', '明信片墙', '查看和搜索已经生成的明信片。'],
  discover: ['DISCOVER · 远方来信', '发现', '浏览并收藏其他用户公开的来信。'],
  mailbox: ['MAILBOX · 用户来信', '信箱', '与其他用户收发信件和附件。'],
  memories: ['MEMORY · 旧日手账', '记忆本', '记录和查看不想忘记的片段。'],
  settings: ['SETTINGS · 工作台抽屉', '设置', '管理账户、故乡和旅程状态。'],
};

App.syncShell = function syncShell() {
  const state = this.state || {};
  const day = document.getElementById('shell-day');
  const hometown = document.getElementById('shell-hometown');
  if (day) day.textContent = `第 ${state.currentDay || 0} 天`;
  if (hometown) hometown.textContent = state.hometown?.hometownName || state.hometown?.county || '尚未设置';
};

App.navigate = function navigate(page) {
  const target = document.getElementById(`page-${page}`);
  if (!target) return;
  if (this.currentPage === 'write_letter' && page !== 'write_letter' && typeof window.saveLetterDraft === 'function') {
    window.saveLetterDraft({ silent: true });
  }
  document.querySelectorAll('#app .page').forEach(node => node.classList.remove('active'));
  target.classList.add('active');
  document.querySelectorAll('.nav-btn').forEach(button => {
    const active = button.dataset.page === page;
    button.classList.toggle('active', active);
    if (active) button.setAttribute('aria-current', 'page');
    else button.removeAttribute('aria-current');
  });
  const [eyebrow, title, subtitle] = WORKBENCH_PAGE_META[page] || WORKBENCH_PAGE_META.game;
  document.getElementById('workspace-eyebrow').textContent = eyebrow;
  document.getElementById('workspace-title').textContent = title;
  document.getElementById('workspace-subtitle').textContent = subtitle;
  this.currentPage = page;
  this.syncShell();
  const fn = `render${page.split('_').map(part => part[0].toUpperCase() + part.slice(1)).join('')}`;
  if (typeof window[fn] === 'function') window[fn]();
  const content = document.getElementById('workspace-content');
  if (content) content.scrollTop = 0;
};

App.createModal = function createModal(content, className = '') {
  document.querySelector('.modal')?.remove();
  const overlay = document.createElement('div');
  overlay.className = `modal workbench-modal ${className}`.trim();
  overlay.setAttribute('role', 'dialog');
  overlay.setAttribute('aria-modal', 'true');
  overlay.addEventListener('click', event => { if (event.target === overlay) overlay.remove(); });
  overlay.innerHTML = content;
  document.body.appendChild(overlay);
  overlay.querySelector('.modal-cl, button, input, textarea')?.focus();
  return overlay;
};

App.showPostcardDetail = function showPostcardDetail(rawPostcard) {
  const pc = this.normalizePostcard(rawPostcard);
  if (!pc) return;
  window._postcardDetail = pc;
  const tags = pc.keywords || pc.tags || [];
  this.createModal(`
    <div class="modal-pnl postcard-detail-panel">
      <button class="modal-cl floating-close" aria-label="关闭" onclick="this.closest('.modal').remove()">×</button>
      <div class="postcard-detail-visual">
        <button class="postcard-detail-frame" aria-label="放大明信片画面" onclick="event.stopPropagation();enlargePostcardImage(this)">${this._imgHtml(pc)}</button>
        <span class="postcard-detail-stamp">故乡<small>LETTER</small></span>
      </div>
      <div class="postcard-detail-copy">
        <span class="section-kicker">POSTCARD · ${this._e(pc.place || '远方')}</span>
        <h3>${this._e(pc.title || '无题明信片')}</h3>
        <div class="modal-meta">${this._e(pc.place || '')}${pc.place && pc.mood ? ' · ' : ''}${this._e(pc.mood || '')}${pc.createdAt ? ` · ${new Date(pc.createdAt).toLocaleDateString('zh-CN')}` : ''}</div>
        ${pc.generationPlace ? `<div class="modal-source-place">画面取景：${this._e(pc.generationPlace)}</div>` : ''}
        <div class="modal-bd">${this._e(pc.body || '这张明信片暂时没有正文。')}</div>
        ${pc.poem ? `<div class="modal-poem">${this._e(pc.poem)}</div>` : ''}
        <div class="modal-tags">${tags.map(tag => `<span class="tag">${this._e(String(tag))}</span>`).join('')}</div>
        ${pc.letterText ? `<div class="letter-echo"><strong>原信内容</strong><p>${this._e(pc.letterText)}</p></div>` : ''}
        <div class="modal-ft postcard-detail-actions">
          <button class="btn btn-pri" onclick="App.exportPostcard(window._postcardDetail, this)">导出 PNG</button>
          <button class="btn btn-sec" onclick="this.closest('.modal').remove()">收好明信片</button>
        </div>
      </div>
    </div>`, 'postcard-modal');
};

App._wrapCanvasText = function wrapCanvasText(ctx, text, maxWidth, maxLines = Infinity) {
  const source = String(text || '').replace(/\r/g, '');
  const lines = [];
  for (const paragraph of source.split('\n')) {
    if (!paragraph) {
      if (lines.length < maxLines) lines.push('');
      continue;
    }
    let line = '';
    for (const char of paragraph) {
      const next = line + char;
      if (line && ctx.measureText(next).width > maxWidth) {
        lines.push(line);
        line = char;
        if (lines.length >= maxLines) break;
      } else {
        line = next;
      }
    }
    if (lines.length >= maxLines) break;
    if (line) lines.push(line);
    if (lines.length >= maxLines) break;
  }
  if (lines.length === maxLines && source.length > lines.join('').length) {
    let last = lines[lines.length - 1].replace(/…$/, '');
    while (last && ctx.measureText(`${last}…`).width > maxWidth) last = last.slice(0, -1);
    lines[lines.length - 1] = `${last}…`;
  }
  return lines;
};

App._loadPostcardExportImage = async function loadPostcardExportImage(url) {
  if (!url) return null;
  const response = await fetch(url);
  if (!response.ok) throw new Error(`图片加载失败：${response.status}`);
  const blob = await response.blob();
  return createImageBitmap(blob);
};

App._drawPostcardExportImage = function drawPostcardExportImage(ctx, image, x, y, width, height) {
  const scale = Math.max(width / image.width, height / image.height);
  const sourceWidth = width / scale;
  const sourceHeight = height / scale;
  const sourceX = (image.width - sourceWidth) / 2;
  const sourceY = (image.height - sourceHeight) / 2;
  ctx.drawImage(image, sourceX, sourceY, sourceWidth, sourceHeight, x, y, width, height);
};

App.exportPostcard = async function exportPostcard(rawPostcard, button) {
  const pc = this.normalizePostcard(rawPostcard);
  if (!pc) return;
  const originalLabel = button?.textContent || '导出 PNG';
  if (button) {
    button.disabled = true;
    button.textContent = '正在导出…';
  }

  try {
    await document.fonts?.ready;
    const canvas = document.createElement('canvas');
    canvas.width = 1800;
    canvas.height = 1200;
    const ctx = canvas.getContext('2d');
    if (!ctx) throw new Error('当前浏览器不支持图片导出');

    const paper = ctx.createLinearGradient(0, 0, 1800, 1200);
    paper.addColorStop(0, '#fff8e8');
    paper.addColorStop(1, '#ead5aa');
    ctx.fillStyle = paper;
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.strokeStyle = '#56331f';
    ctx.lineWidth = 24;
    ctx.strokeRect(38, 38, 1724, 1124);
    ctx.strokeStyle = '#b77c47';
    ctx.lineWidth = 4;
    ctx.setLineDash([14, 10]);
    ctx.strokeRect(62, 62, 1676, 1076);
    ctx.setLineDash([]);

    const imageBox = { x: 100, y: 100, width: 990, height: 760 };
    ctx.fillStyle = '#d6bd8e';
    ctx.fillRect(imageBox.x - 12, imageBox.y - 12, imageBox.width + 24, imageBox.height + 24);
    let image = null;
    try {
      image = await this._loadPostcardExportImage(pc.imageUrl);
    } catch (error) {
      console.warn('[postcard-export] 无法读取原图，改用图片缺失样式', error);
    }
    if (image) {
      this._drawPostcardExportImage(ctx, image, imageBox.x, imageBox.y, imageBox.width, imageBox.height);
      image.close?.();
    } else {
      const fallback = ctx.createLinearGradient(imageBox.x, imageBox.y, imageBox.x + imageBox.width, imageBox.y + imageBox.height);
      fallback.addColorStop(0, '#718b78');
      fallback.addColorStop(.55, '#b9aa7d');
      fallback.addColorStop(1, '#d8b274');
      ctx.fillStyle = fallback;
      ctx.fillRect(imageBox.x, imageBox.y, imageBox.width, imageBox.height);
      ctx.fillStyle = 'rgba(255,248,226,.88)';
      ctx.textAlign = 'center';
      ctx.font = '38px "Microsoft YaHei", sans-serif';
      ctx.fillText('图片暂不可用', imageBox.x + imageBox.width / 2, imageBox.y + imageBox.height / 2);
    }

    const title = pc.title || '无题明信片';
    const place = pc.place || pc.generationPlace || '沿途';
    const mood = pc.mood || '';
    const date = pc.createdAt ? new Date(pc.createdAt).toLocaleDateString('zh-CN') : '';
    const meta = [place, mood, date].filter(Boolean).join('  ·  ');
    const body = pc.body || pc.letterText || '这一刻没有留下太多文字，却把沿途的光好好收进了明信片。';
    const tags = pc.keywords || pc.tags || [];

    ctx.textAlign = 'left';
    ctx.fillStyle = '#873e3d';
    ctx.font = '24px Zpix, "Microsoft YaHei", sans-serif';
    ctx.fillText('HOMETOWN LETTERS · 故乡来信', 1160, 145);
    ctx.fillStyle = '#3b291f';
    ctx.font = 'bold 48px Zpix, "Microsoft YaHei", sans-serif';
    const titleLines = this._wrapCanvasText(ctx, title, 510, 3);
    titleLines.forEach((line, lineIndex) => ctx.fillText(line, 1160, 225 + lineIndex * 66));

    const metaY = 245 + titleLines.length * 66;
    ctx.fillStyle = '#7d6656';
    ctx.font = '25px "Microsoft YaHei", sans-serif';
    this._wrapCanvasText(ctx, meta, 510, 2).forEach((line, lineIndex) => ctx.fillText(line, 1160, metaY + lineIndex * 38));
    ctx.strokeStyle = 'rgba(83,50,31,.35)';
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.moveTo(1160, metaY + 76);
    ctx.lineTo(1660, metaY + 76);
    ctx.stroke();

    ctx.fillStyle = '#4e392c';
    ctx.font = '29px "Microsoft YaHei", sans-serif';
    const bodyLines = this._wrapCanvasText(ctx, body, 500, 12);
    bodyLines.forEach((line, lineIndex) => ctx.fillText(line, 1160, metaY + 132 + lineIndex * 48));

    if (tags.length) {
      ctx.fillStyle = '#6f5848';
      ctx.font = '22px "Microsoft YaHei", sans-serif';
      const tagText = tags.slice(0, 5).map(tag => `#${tag}`).join('  ');
      ctx.fillText(tagText, 1160, 1030);
    }

    ctx.save();
    ctx.translate(1555, 135);
    ctx.rotate(.06);
    ctx.fillStyle = '#873e3d';
    ctx.fillRect(0, 0, 120, 142);
    ctx.strokeStyle = '#f0ca88';
    ctx.lineWidth = 6;
    ctx.strokeRect(9, 9, 102, 124);
    ctx.fillStyle = '#f7dfae';
    ctx.textAlign = 'center';
    ctx.font = 'bold 25px Zpix, "Microsoft YaHei", sans-serif';
    ctx.fillText('故乡', 60, 67);
    ctx.font = '16px Zpix, "Microsoft YaHei", sans-serif';
    ctx.fillText('LETTER', 60, 98);
    ctx.restore();

    ctx.fillStyle = '#6f5848';
    ctx.textAlign = 'left';
    ctx.font = '24px "Microsoft YaHei", sans-serif';
    ctx.fillText(pc.generationPlace ? `画面取景：${pc.generationPlace}` : `寄自：${place}`, 100, 930);
    ctx.fillStyle = '#873e3d';
    ctx.font = '22px Zpix, "Microsoft YaHei", sans-serif';
    ctx.fillText('把今天寄给过去，也把沿途的光留给未来。', 100, 1010);

    const blob = await new Promise((resolve, reject) => {
      canvas.toBlob(result => result ? resolve(result) : reject(new Error('无法生成 PNG 文件')), 'image/png');
    });
    const link = document.createElement('a');
    const safeName = `${place}-${title}`.replace(/[\\/:*?"<>|\s]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 60) || '故乡明信片';
    const objectUrl = URL.createObjectURL(blob);
    link.href = objectUrl;
    link.download = `故乡来信-${safeName}.png`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
    this.showToast('明信片已导出为 PNG');
  } catch (error) {
    console.error('[postcard-export] 导出失败', error);
    this.showToast(this.friendlyError(error, '导出失败，请稍后重试'), 3800);
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = originalLabel;
    }
  }
};
