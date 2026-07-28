/* ================================================================
   故乡来信 · 写信交互 (WriteLetterScene)
   四步骤：写信 → 装信封 → 贴邮戳 → 投递
   ================================================================ */

const LetterStep = Object.freeze({
  WRITING:  'writing',
  SEALING:  'sealing',
  STAMPED:  'stamped',
  SENDING:  'sending',
  SUCCESS:  'success',
  ERROR:    'error',
});

let _curStep = LetterStep.WRITING;
let _busy = false;
let _errorTimer = null;
let _stampApplied = false;   // 邮戳是否已贴
let _generation = 0;          // 递增计数器，用于拦截过期异步操作
let _draftTimer = null;
let _activeDraftKey = null;
let _referenceImageFile = null;
let _referenceImageUrl = '';
let _imageStyles = null;
let _defaultImageStyleId = 'pixel_16bit';
let _imageStylesPromise = null;
let _styleSavePromise = Promise.resolve(true);

const LETTER_DRAFT_VERSION = 1;
const MAX_REFERENCE_IMAGE_BYTES = 10 * 1024 * 1024;
const ALLOWED_REFERENCE_IMAGE_TYPES = new Set(['image/jpeg', 'image/png', 'image/webp']);

function _letterDraftKey() {
  const user = typeof Auth !== 'undefined' ? Auth.getUser() : null;
  const owner = user?.id || user?.username || 'guest';
  return `hometown_letter_draft_v${LETTER_DRAFT_VERSION}_${String(owner)}`;
}

function _readLetterDraft() {
  try {
    const raw = localStorage.getItem(_activeDraftKey || _letterDraftKey());
    if (!raw) return null;
    const draft = JSON.parse(raw);
    if (!draft || draft.version !== LETTER_DRAFT_VERSION) return null;
    return draft;
  } catch (error) {
    console.warn('[write-letter] 无法读取本地草稿', error);
    return null;
  }
}

function _draftTimeLabel(timestamp) {
  return App.relativeTime(timestamp) || '刚刚';
}

function _setDraftStatus(message, hasDraft = true) {
  const status = document.getElementById('env-draft-status');
  const clearButton = document.getElementById('env-clear-draft');
  if (status) status.textContent = message;
  if (clearButton) clearButton.hidden = !hasDraft;
}

function saveLetterDraft({ silent = false } = {}) {
  if (_draftTimer) { clearTimeout(_draftTimer); _draftTimer = null; }
  if (_curStep === LetterStep.SUCCESS) return false;
  const textarea = document.getElementById('env-textarea');
  const place = document.getElementById('env-place');
  const mood = document.getElementById('env-mood');
  if (!textarea && !place && !mood) return false;

  const draft = {
    version: LETTER_DRAFT_VERSION,
    text: textarea?.value || '',
    place: place?.value || '',
    mood: mood?.value || '',
    updatedAt: Date.now(),
  };
  const hasContent = Boolean(draft.text.trim() || draft.place.trim() || draft.mood.trim());

  try {
    const storageKey = _activeDraftKey || _letterDraftKey();
    if (hasContent) localStorage.setItem(storageKey, JSON.stringify(draft));
    else localStorage.removeItem(storageKey);
    if (!silent) _setDraftStatus(hasContent ? '草稿已保存 · 刚刚' : '草稿自动保存', hasContent);
    return true;
  } catch (error) {
    console.warn('[write-letter] 无法保存本地草稿', error);
    if (!silent) _setDraftStatus('草稿保存失败，请勿关闭页面', hasContent);
    return false;
  }
}

function _scheduleLetterDraftSave() {
  // 输入发生时立即落盘，防抖只用于减少状态文字闪动。
  // 这样即使用户下一刻就切页，也不会丢掉最后几个字。
  const saved = saveLetterDraft({ silent: true });
  const hasContent = Boolean(
    document.getElementById('env-textarea')?.value.trim() ||
    document.getElementById('env-place')?.value.trim() ||
    document.getElementById('env-mood')?.value.trim()
  );
  if (!saved) {
    _setDraftStatus('草稿保存失败，请勿关闭页面', hasContent);
    return;
  }
  _setDraftStatus(hasContent ? '草稿已保存' : '草稿自动保存', hasContent);
  _draftTimer = setTimeout(() => {
    _draftTimer = null;
    _setDraftStatus(hasContent ? '草稿已保存 · 刚刚' : '草稿自动保存', hasContent);
  }, 450);
}

function clearLetterDraft() {
  if (!window.confirm('确定清空这封尚未寄出的草稿吗？')) return;
  _clearStoredLetterDraft();
  removeLetterReferenceImage({ silent: true });
  ['env-textarea', 'env-place', 'env-mood'].forEach(id => {
    const field = document.getElementById(id);
    if (field) field.value = '';
  });
  _setDraftStatus('草稿已清空', false);
  document.getElementById('env-textarea')?.focus({ preventScroll: true });
}

function _restoreLetterDraft() {
  const draft = _readLetterDraft();
  if (!draft) {
    _setDraftStatus('草稿自动保存', false);
    return false;
  }
  const fields = [
    ['env-textarea', draft.text],
    ['env-place', draft.place],
    ['env-mood', draft.mood],
  ];
  fields.forEach(([id, value]) => {
    const field = document.getElementById(id);
    if (field) field.value = value || '';
  });
  _setDraftStatus(`已恢复${_draftTimeLabel(draft.updatedAt)}的草稿`, true);
  return true;
}

function _clearStoredLetterDraft() {
  if (_draftTimer) { clearTimeout(_draftTimer); _draftTimer = null; }
  try { localStorage.removeItem(_activeDraftKey || _letterDraftKey()); } catch (error) {
    console.warn('[write-letter] 无法清除本地草稿', error);
  }
}

function _syncReferenceImagePreview() {
  const preview = document.getElementById('env-reference-preview');
  const empty = document.getElementById('env-reference-empty');
  const box = document.getElementById('env-reference-box');
  const removeButton = document.getElementById('env-reference-remove');
  const name = document.getElementById('env-reference-name');
  const hint = document.getElementById('env-reference-hint');
  const hasImage = Boolean(_referenceImageFile && _referenceImageUrl);

  if (preview) {
    preview.hidden = !hasImage;
    if (hasImage) preview.src = _referenceImageUrl;
    else preview.removeAttribute('src');
  }
  if (empty) empty.hidden = hasImage;
  if (box) box.classList.toggle('has-image', hasImage);
  if (removeButton) removeButton.hidden = !hasImage;
  if (name) name.textContent = hasImage ? _referenceImageFile.name : '选择参考图片';
  if (hint) {
    hint.textContent = hasImage
      ? '生成明信片时会参考这张图片'
      : '未选择时，将根据地点提示生成画面';
  }
}

function chooseLetterReferenceImage(event) {
  const input = event?.target;
  const file = input?.files?.[0];
  if (!file) return;

  if (!ALLOWED_REFERENCE_IMAGE_TYPES.has(file.type)) {
    App.showToast('参考图片仅支持 JPEG、PNG 或 WebP', 3500);
    input.value = '';
    return;
  }
  if (file.size > MAX_REFERENCE_IMAGE_BYTES) {
    App.showToast('参考图片不能超过 10 MB', 3500);
    input.value = '';
    return;
  }

  if (_referenceImageUrl) URL.revokeObjectURL(_referenceImageUrl);
  _referenceImageFile = file;
  _referenceImageUrl = URL.createObjectURL(file);
  _syncReferenceImagePreview();
}

function removeLetterReferenceImage({ silent = false } = {}) {
  if (_referenceImageUrl) URL.revokeObjectURL(_referenceImageUrl);
  _referenceImageFile = null;
  _referenceImageUrl = '';
  const input = document.getElementById('env-reference-input');
  if (input) input.value = '';
  _syncReferenceImagePreview();
  if (!silent) App.showToast('参考图片已移除，将根据地点提示生成画面', 2800);
}

function _syncImageStyleOptions() {
  const select = document.getElementById('env-image-style');
  const status = document.getElementById('env-style-status');
  if (!select || !_imageStyles?.length) return;

  const availableIds = new Set(_imageStyles.map(style => style.id));
  const fallbackId = availableIds.has(_defaultImageStyleId)
    ? _defaultImageStyleId
    : _imageStyles[0].id;
  const selectedId = availableIds.has(App.state.imageStyle)
    ? App.state.imageStyle
    : fallbackId;

  App.state.imageStyle = selectedId;
  select.innerHTML = _imageStyles.map(style =>
    `<option value="${App._e(style.id)}"${style.id === selectedId ? ' selected' : ''}>${App._e(style.label)}</option>`
  ).join('');
  select.disabled = false;
  if (status) status.textContent = '选择后自动保存';
}

async function _loadImageStyles() {
  if (_imageStyles?.length) {
    _syncImageStyleOptions();
    return _imageStyles;
  }
  if (!_imageStylesPromise) {
    _imageStylesPromise = api.getImageStyles()
      .then(response => {
        if (!response?.ok || !Array.isArray(response.data?.styles) || !response.data.styles.length) {
          throw new Error(response?.error || '当前没有可用画风');
        }
        _imageStyles = response.data.styles.filter(style => style?.id && style?.label);
        if (!_imageStyles.length) throw new Error('当前没有可用画风');
        _defaultImageStyleId = response.data.defaultStyleId || 'pixel_16bit';
        return _imageStyles;
      })
      .catch(error => {
        _imageStylesPromise = null;
        throw error;
      });
  }

  try {
    await _imageStylesPromise;
    _syncImageStyleOptions();
    return _imageStyles;
  } catch (error) {
    const select = document.getElementById('env-image-style');
    const status = document.getElementById('env-style-status');
    const needsLogin = error?.status === 401 || error?.message === '未登录';
    if (select) {
      select.innerHTML = `<option>${needsLogin ? '登录后可选择' : '画风加载失败'}</option>`;
      select.disabled = true;
    }
    if (status) {
      status.textContent = needsLogin
        ? '登录后可以选择并保存画风'
        : App.friendlyError(error, '画风加载失败，请稍后重试');
    }
    return [];
  }
}

function saveLetterImageStyle(styleId) {
  const select = document.getElementById('env-image-style');
  const status = document.getElementById('env-style-status');
  const previousId = App.state.imageStyle || _defaultImageStyleId;
  if (!styleId || styleId === previousId) return _styleSavePromise;

  if (select) select.disabled = true;
  if (status) status.textContent = '正在保存…';

  _styleSavePromise = api.setImageStyle(styleId)
    .then(response => {
      if (!response?.ok) throw new Error(response?.error || '画风保存失败');
      App.state.imageStyle = response.data?.imageStyle || styleId;
      if (status?.isConnected) status.textContent = '画风已保存';
      return true;
    })
    .catch(error => {
      if (select?.isConnected) select.value = previousId;
      if (status?.isConnected) status.textContent = '保存失败，已恢复原选择';
      App.showToast(App.friendlyError(error, '画风保存失败，请稍后重试'), 3800);
      return false;
    })
    .finally(() => {
      if (select?.isConnected) select.disabled = false;
    });

  return _styleSavePromise;
}

/* ================ RENDER ================ */

function renderWriteLetter() {
  const el = document.getElementById('page-write_letter');
  if (!el) return;
  _activeDraftKey = _letterDraftKey();

  const ls = (App.state.letters || []).slice(0, 6);

  el.innerHTML = `
    <div class="write-grid env-scene writing" id="env-scene">
      <section class="letter-work-area">
        <div class="env-letter-card" id="env-letter-card">
          <div class="letter-date">TO MY PAST SELF · 第 ${App.state.currentDay || 0} 天</div>
          <div class="env-writing-row">
            <textarea class="env-textarea" id="env-textarea" placeholder="写下想对过去说的话…" rows="9" maxlength="2000"></textarea>
            <aside class="env-reference-card" aria-label="明信片参考图片与画风">
              <span class="env-reference-kicker">REFERENCE IMAGE</span>
              <div class="env-reference-box" id="env-reference-box">
                <input type="file" id="env-reference-input" accept="image/jpeg,image/png,image/webp" onchange="chooseLetterReferenceImage(event)" hidden>
                <button type="button" class="env-reference-trigger" onclick="document.getElementById('env-reference-input').click()" aria-label="选择参考图片">
                  <img id="env-reference-preview" alt="已选择的参考图片预览" hidden>
                  <span class="env-reference-empty" id="env-reference-empty" aria-hidden="true"><b>＋</b><small>选择图片</small></span>
                </button>
                <span class="env-reference-pin" aria-hidden="true"></span>
              </div>
              <strong id="env-reference-name">选择参考图片</strong>
              <p id="env-reference-hint">未选择时，将根据地点提示生成画面</p>
              <button type="button" class="env-reference-remove" id="env-reference-remove" onclick="removeLetterReferenceImage()" hidden>移除图片</button>
              <label class="env-style-picker" for="env-image-style">
                <span>明信片画风</span>
                <select id="env-image-style" onchange="saveLetterImageStyle(this.value)" disabled>
                  <option>正在加载画风…</option>
                </select>
                <small id="env-style-status" aria-live="polite">正在加载可用画风…</small>
              </label>
            </aside>
          </div>
          <div class="env-extra"><div class="env-form-row">
            <label class="env-form-group">地点提示（可选）<input class="env-inp" id="env-place" placeholder="例如：河堤、学校后门、旧市场"></label>
            <label class="env-form-group">情绪提示（可选）<input class="env-inp" id="env-mood" placeholder="例如：平静、怀念、鼓起勇气"></label>
          </div></div>
          <div class="env-draft-bar"><span id="env-draft-status" aria-live="polite">草稿自动保存</span><button type="button" id="env-clear-draft" class="env-clear-draft" onclick="clearLetterDraft()" hidden>清空草稿</button></div>
          <div class="env-step-btns" id="env-step-btns"></div>
          <div class="env-status" id="env-status" aria-live="polite">&nbsp;</div>
        </div>
        <div class="env-envelope-wrap" id="env-envelope-wrap">
          <button type="button" class="env-envelope" id="env-envelope" onclick="enlargeEnvelope()" aria-label="查看信封">
            <img class="env-envelope-art closed" src="assets/workbench/letters/envelope-closed.png" alt="闭合的复古信封">
            <img class="env-envelope-art open" src="assets/workbench/letters/envelope-open.png" alt="打开的复古信封">
            <img class="env-stamp" id="env-stamp" src="assets/workbench/letters/stamp.png" alt="复古邮票">
            <span class="env-postmark" id="env-postmark"><span class="env-postmark-inner">故乡<br>${new Date().getFullYear()}</span></span>
          </button>
          <div class="env-step-btns" id="env-env-btns"></div>
          <div class="env-status" id="env-env-status" aria-live="polite">&nbsp;</div>
        </div>
      </section>
      <aside class="write-side">
        <section class="dark-panel delivery-note"><span class="section-kicker">DELIVERY GUIDE</span><h3>投递步骤</h3><ol><li>写下想说的话</li><li>装进信封并贴上邮票</li><li>投递后生成明信片</li></ol><div class="env-mailbox" id="env-mailbox"><img src="assets/workbench/letters/mailbox.png" alt="打开的乡间邮箱"></div></section>
        <section class="paper-panel recent-letters"><div class="panel-heading"><div><span class="section-kicker">RECENT LETTERS</span><h3>最近投递的信</h3></div></div><div class="env-recent" id="env-recent">${ls.length ? ls.map(_renderRecentItem).join('') : '<div class="rl-empty">还没有投递过信。</div>'}</div></section>
      </aside>
    </div>
  `;

  _curStep = LetterStep.WRITING;
  _busy = false;
  _stampApplied = false;
  _generation++;  // 标记新一轮渲染，废弃之前的异步操作
  _renderButtons();
  _restoreLetterDraft();
  _syncReferenceImagePreview();
  _loadImageStyles();
  ['env-textarea', 'env-place', 'env-mood'].forEach(id => {
    document.getElementById(id)?.addEventListener('input', _scheduleLetterDraftSave);
  });

  // 聚焦 textarea
  setTimeout(() => {
    const ta = document.getElementById('env-textarea');
    if (ta) ta.focus({ preventScroll: true });
  }, 100);
}

function _renderButtons() {
  // WRITING: buttons on letter card.  STAMPED: buttons on envelope.
  const cardBtns = document.getElementById('env-step-btns');
  const envBtns = document.getElementById('env-env-btns');

  switch (_curStep) {
    case LetterStep.WRITING:
      if (cardBtns) {
        cardBtns.style.display = '';
        cardBtns.innerHTML = `
          <button class="env-btn env-btn-seal" id="btn-seal" onclick="sealLetter()">
            装进信封
          </button>`;
      }
      if (envBtns) envBtns.style.display = 'none';
      break;
    case LetterStep.STAMPED:
      if (cardBtns) cardBtns.style.display = 'none';
      if (envBtns) {
        envBtns.style.display = '';
        if (!_stampApplied) {
          envBtns.innerHTML = `
            <button class="env-btn env-btn-stamp" id="btn-stamp" onclick="applyStamp()">
              贴上邮票
            </button>`;
        } else {
          envBtns.innerHTML = `
            <button class="env-btn env-btn-send" id="btn-send" onclick="deliverLetter()">
              投进邮箱
            </button>`;
        }
      }
      break;
  }
}

function _renderRecentItem(l) {
  const g = App._imgGradient(l.place, l.mood);
  return `
    <div class="rl-item">
      <div class="rl-thumb" style="background:${g}">@</div>
      <div class="rl-info">
        <div class="rl-text">${App._e(l.text)}</div>
        <div class="rl-meta">
          ${l.place ? `${App._e(l.place)}` : ''}
          ${l.mood ? ` · ${App._e(l.mood)}` : ''}
          ${l.timestamp ? ` · ${new Date(l.timestamp).toLocaleString('zh-CN')}` : ''}
        </div>
      </div>
    </div>`;
}


/* ================ STEP 1→2: 装进信封 ================ */

function sealLetter() {
  if (_busy || _curStep !== LetterStep.WRITING) return;

  const ta = document.getElementById('env-textarea');
  const text = ta ? ta.value.trim() : '';
  if (!text) {
    const s = document.getElementById('env-status');
    if (s) s.textContent = '先写下一些话再装信封吧';
    return;
  }

  _busy = true;
  _curStep = LetterStep.SEALING;

  const scene = document.getElementById('env-scene');
  if (scene) {
    scene.classList.remove('writing');
    scene.classList.add('sealing');
  }

  // 切换到信封上的状态显示
  const cardStatus = document.getElementById('env-status');
  if (cardStatus) cardStatus.style.display = 'none';

  const envBtns = document.getElementById('env-step-btns');
  if (envBtns) envBtns.style.display = 'none';

  const envStatus = document.getElementById('env-env-status');
  if (envStatus) { envStatus.style.display = ''; envStatus.textContent = '正在装进信封…'; }

  // 0.6s 动画后进入 STAMPED
  setTimeout(() => {
    _curStep = LetterStep.STAMPED;
    _busy = false;

    if (scene) {
      scene.classList.remove('sealing');
      scene.classList.add('stamped');
    }
    if (envStatus) envStatus.textContent = '请给信封贴上邮票';

    // 显示信封上的按钮
    _renderButtons();
  }, 600);
}


/* ================ STEP 2→3: 贴邮戳 ================ */

function applyStamp() {
  if (_busy || _curStep !== LetterStep.STAMPED || _stampApplied) return;

  _busy = true;
  _stampApplied = true;

  // 给信封加上 stamp-applied 类，触发邮戳 CSS 动画
  const scene = document.getElementById('env-scene');
  if (scene) scene.classList.add('stamp-applied');

  const status = document.getElementById('env-env-status');
  if (status) status.textContent = '邮票已贴好';

  _renderButtons();
  _busy = false;
}


/* ================ STEP 3→4: 投递 ================ */

async function deliverLetter() {
  if (_busy || _curStep !== LetterStep.STAMPED || !_stampApplied) return;

  await _styleSavePromise;
  if (_busy || _curStep !== LetterStep.STAMPED || !_stampApplied) return;

  const ta = document.getElementById('env-textarea');
  const text = ta ? ta.value.trim() : '';
  if (!text) return;

  _busy = true;
  _curStep = LetterStep.SENDING;
  const gen = _generation;  // 捕获当前 generation，用于后续守卫

  const scene = document.getElementById('env-scene');
  const status = document.getElementById('env-env-status');

  if (scene) {
    scene.classList.remove('stamped');
    scene.classList.add('sending');
  }
  if (status) { status.style.display = ''; status.textContent = '正在投递并生成明信片…'; }

  // 信封按钮隐藏
  const envBtns = document.getElementById('env-env-btns');
  if (envBtns) envBtns.style.display = 'none';

  // Start API call
  const place = document.getElementById('env-place');
  const mood = document.getElementById('env-mood');
  const placeHint = place ? place.value.trim() : '';
  const moodHint = mood ? mood.value.trim() : '';
  const sendFn = _referenceImageFile
    ? api.sendLetterWithImage(text, placeHint, moodHint, _referenceImageFile)
    : api.sendLetter(text, placeHint, moodHint);
  const apiPromise = sendFn.catch(e => ({ ok: false, error: e.message || '网络错误' }));

  // Wait for envelope fade, then fly animation
  await _sleep(300);
  if (_generation !== gen) { _busy = false; return; }
  _animateEnvelopeToMailbox();

  // Wait for API + animation
  const [apiResult] = await Promise.all([
    apiPromise,
    _sleep(1200)
  ]);
  if (_generation !== gen) { _busy = false; return; }

  if (scene) scene.classList.remove('sending');

  if (apiResult && apiResult.ok) {
    // → SUCCESS
    _curStep = LetterStep.SUCCESS;
    _clearStoredLetterDraft();
    removeLetterReferenceImage({ silent: true });
    if (scene) scene.classList.add('success');
    if (status) status.textContent = '投递成功，明信片已生成';

    try {
      const sr = await api.getState();
      if (_generation !== gen) { _busy = false; return; }
      if (sr.ok) {
        App.applyState(sr.data);
      }
    } catch (e) { console.warn('[write-letter] state refresh failed:', e); }

    const _savedGen = gen;
    setTimeout(() => {
      if (_generation !== _savedGen) return;
      if (apiResult.data) App.showPostcardDetail(apiResult.data);
      _resetScene(false);
    }, 600);

  } else {
    // → ERROR
    if (_generation !== gen) { _busy = false; return; }
    _curStep = LetterStep.ERROR;
    if (scene) scene.classList.add('error');

    const errMsg = App.friendlyError(apiResult ? (apiResult.error || '投递失败') : '网络错误', '投递失败，请稍后重试');
    if (status) status.textContent = errMsg;
    App.showToast(errMsg, 4000);

    if (_errorTimer) clearTimeout(_errorTimer);
    const _savedGen = gen;
    _errorTimer = setTimeout(() => {
      if (_generation !== _savedGen) return;
      _resetScene();
    }, 3000);
  }

  _busy = false;
}


/* ================ 信封飞行动画 ================ */

function _animateEnvelopeToMailbox() {
  const env = document.getElementById('env-envelope');
  const mailbox = document.getElementById('env-mailbox');
  if (!env || !mailbox) return;

  const envRect = env.getBoundingClientRect();
  const mailboxRect = mailbox.getBoundingClientRect();

  const clone = env.cloneNode(true);
  clone.id = '';
  clone.style.position = 'fixed';
  clone.style.left   = envRect.left + 'px';
  clone.style.top    = envRect.top + 'px';
  clone.style.width  = envRect.width + 'px';
  clone.style.height = envRect.height + 'px';
  clone.style.margin = '0';
  clone.style.zIndex = '1000';
  clone.style.pointerEvents = 'none';
  clone.style.animation = 'none';
  clone.style.display = 'block';
  clone.style.transition = 'all 1.2s cubic-bezier(0.4, 0, 0.2, 1)';
  clone.style.opacity = '0.9';

  // 附加到 scene 容器中，页面重新渲染时自动清除
  const scene = document.getElementById('env-scene');
  if (scene) scene.appendChild(clone); else document.body.appendChild(clone);

  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      const targetX = mailboxRect.left + mailboxRect.width / 2 - envRect.width * 0.1;
      const targetY = mailboxRect.top + mailboxRect.height / 2 - envRect.height * 0.1;
      clone.style.left     = targetX + 'px';
      clone.style.top      = targetY + 'px';
      clone.style.transform = 'scale(0.15) rotate(10deg)';
      clone.style.opacity  = '0.15';
    });
  });

  setTimeout(() => {
    if (clone.parentNode) clone.remove();
  }, 1300);
}


/* ================ RESET ================ */

function _resetScene(preserveInput = true) {
  if (_errorTimer) { clearTimeout(_errorTimer); _errorTimer = null; }

  // Preserve user input
  const oldTa = document.getElementById('env-textarea');
  const oldPlace = document.getElementById('env-place');
  const oldMood = document.getElementById('env-mood');
  const savedText = preserveInput && oldTa ? oldTa.value : '';
  const savedPlace = preserveInput && oldPlace ? oldPlace.value : '';
  const savedMood = preserveInput && oldMood ? oldMood.value : '';

  _curStep = LetterStep.WRITING;
  _busy = false;
  _stampApplied = false;

  renderWriteLetter();

  const newTa = document.getElementById('env-textarea');
  const newPlace = document.getElementById('env-place');
  const newMood = document.getElementById('env-mood');
  if (newTa && savedText) newTa.value = savedText;
  if (newPlace && savedPlace) newPlace.value = savedPlace;
  if (newMood && savedMood) newMood.value = savedMood;
}


/* ================ 信封点击放大 ================ */

function enlargeEnvelope() {
  if (_curStep !== LetterStep.STAMPED) return;

  const env = document.getElementById('env-envelope');
  if (!env) return;

  // 创建全屏遮罩
  const overlay = document.createElement('div');
  overlay.className = 'env-overlay';

  // 克隆信封
  const clone = env.cloneNode(true);
  clone.id = 'env-envelope-large';
  clone.onclick = null; // 移除 onclick 防递归
  clone.style.pointerEvents = 'none';

  overlay.appendChild(clone);

  // 点击遮罩关闭
  overlay.addEventListener('click', () => {
    overlay.remove();
  });

  document.body.appendChild(overlay);
}


/* ================ UTILITY ================ */

function _sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

window.addEventListener('pagehide', () => saveLetterDraft({ silent: true }));
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'hidden') saveLetterDraft({ silent: true });
});
