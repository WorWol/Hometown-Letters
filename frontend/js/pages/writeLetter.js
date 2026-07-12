/* ================================================================
   故乡来信 · 写信交互 (WriteLetterScene)
   v6 — 四步骤：写信 → 装信封 → 贴邮戳 → 投递
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

/* ================ RENDER ================ */

function renderWriteLetter() {
  const el = document.getElementById('page-write_letter');
  if (!el) return;

  const ls = (App.state.letters || []).slice(0, 6);

  el.innerHTML = `
    <div class="env-scene" id="env-scene">

      <!-- 步骤 1: 信纸 -->
      <div class="env-letter-card" id="env-letter-card">
        <textarea class="env-textarea" id="env-textarea"
          placeholder="写一封给过去自己的信……"
          rows="5" maxlength="2000"></textarea>
        <div class="env-extra">
          <div class="env-form-row">
            <div class="env-form-group">
              <label>推荐地点（可选）</label>
              <input class="env-inp" id="env-place" placeholder="河堤 / 学校后门 / 旧市场">
            </div>
            <div class="env-form-group">
              <label>希望的情绪（可选）</label>
              <input class="env-inp" id="env-mood" placeholder="平静 / 鼓起勇气">
            </div>
          </div>
        </div>

        <div class="env-step-btns" id="env-step-btns">
          <!-- 按钮由 _renderButtons() 动态填充 -->
        </div>
        <div class="env-status" id="env-status">&nbsp;</div>
      </div>

      <!-- 步骤 2-4: 信封 + 邮戳 + 邮票 -->
      <div class="env-envelope" id="env-envelope" onclick="enlargeEnvelope()">
        <div class="env-stamp" id="env-stamp"></div>
        <div class="env-postmark" id="env-postmark"></div>
        <div class="env-step-btns" id="env-env-btns" style="margin-top: 300px; display: none;">
          <!-- 信封上的按钮 -->
        </div>
        <div class="env-status" id="env-env-status" style="margin-top: 8px; display: none;">&nbsp;</div>
      </div>

      <!-- 最近的信 -->
      <div class="env-recent" id="env-recent">
        <div class="rl-title">最近写过的信</div>
        ${ls.length === 0
          ? '<div class="rl-empty">还没有寄出过信。</div>'
          : ls.map(_renderRecentItem).join('')}
      </div>

    </div>

    <!-- 邮箱 -->
    <div class="env-mailbox" id="env-mailbox">
      <img src="assets/env_mailbox.png" alt="邮箱">
    </div>
  `;

  _curStep = LetterStep.WRITING;
  _busy = false;
  _stampApplied = false;
  _generation++;  // 标记新一轮渲染，废弃之前的异步操作
  _renderButtons();

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
              贴邮戳
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
  if (envStatus) { envStatus.style.display = ''; envStatus.textContent = '正在装进信封……'; }

  // 0.6s 动画后进入 STAMPED
  setTimeout(() => {
    _curStep = LetterStep.STAMPED;
    _busy = false;

    if (scene) {
      scene.classList.remove('sealing');
      scene.classList.add('stamped');
    }
    if (envStatus) envStatus.textContent = '给信封贴上邮戳吧';

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
  if (status) status.textContent = '邮戳已贴好！';

  _renderButtons();
  _busy = false;
}


/* ================ STEP 3→4: 投递 ================ */

async function deliverLetter() {
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
  if (status) { status.style.display = ''; status.textContent = '投递中……'; }

  // 信封按钮隐藏
  const envBtns = document.getElementById('env-env-btns');
  if (envBtns) envBtns.style.display = 'none';

  // Start API call
  const place = document.getElementById('env-place');
  const mood = document.getElementById('env-mood');
  const sendFn = api.sendLetter(text, place ? place.value.trim() : '', mood ? mood.value.trim() : '');
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
    if (scene) scene.classList.add('success');
    if (status) status.textContent = '投递成功！';

    try {
      const sr = await api.getState();
      if (_generation !== gen) { _busy = false; return; }
      if (sr.ok) {
        App.state.letters = sr.data.letters || [];
        App.state.postcards = sr.data.postcards || [];
        App.state.currentDay = sr.data.current_day || 0;
      }
    } catch (e) { console.warn('[writeLetter] state refresh failed:', e); }

    const _savedGen = gen;
    setTimeout(() => {
      if (_generation !== _savedGen) return;
      if (apiResult.data) App.showPostcardDetail(apiResult.data);
      _resetScene();
    }, 600);

  } else {
    // → ERROR
    if (_generation !== gen) { _busy = false; return; }
    _curStep = LetterStep.ERROR;
    if (scene) scene.classList.add('error');

    const errMsg = apiResult ? (apiResult.error || '未能寄出') : '网络错误';
    if (status) status.textContent = errMsg;
    App.showToast('寄信失败：' + errMsg, 4000);

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

function _resetScene() {
  if (_errorTimer) { clearTimeout(_errorTimer); _errorTimer = null; }

  // Preserve user input
  const oldTa = document.getElementById('env-textarea');
  const oldPlace = document.getElementById('env-place');
  const oldMood = document.getElementById('env-mood');
  const savedText = oldTa ? oldTa.value : '';
  const savedPlace = oldPlace ? oldPlace.value : '';
  const savedMood = oldMood ? oldMood.value : '';

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
