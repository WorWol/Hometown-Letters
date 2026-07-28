/* 新人首次登录聚光灯引导。 */

const Onboarding = (() => {
  const VERSION = 1;
  const steps = [
    {
      page: 'game',
      selector: '.workspace-topbar',
      eyebrow: 'WELCOME · 灯已经亮起',
      title: '欢迎来到故乡来信',
      body: '桌面会显示旅程天数、故乡、最近生成的明信片和记录。',
    },
    {
      page: 'settings',
      selector: '.hometown-card',
      eyebrow: 'STEP 1 · 找到邮路起点',
      title: '先写下你的故乡',
      body: '填写省、市、区县和故乡名称。现在也可以跳过，稍后在设置中补充。',
    },
    {
      page: 'write_letter',
      selector: '#env-textarea',
      eyebrow: 'STEP 2 · 写给过去',
      title: '把今天放进信纸',
      body: '写下想说的话，再装进信封、贴上邮票并投递。投递成功后会生成明信片，草稿也会自动保存。',
    },
    {
      page: 'write_letter',
      selector: '.env-reference-card',
      eyebrow: 'STEP 3 · 决定明信片的画面',
      title: '照片与画风都由你选择',
      body: '参考图片和画风会影响生成结果。未选择图片时，将根据地点提示生成画面。',
    },
    {
      page: 'write_letter',
      selector: '.rail-nav',
      eyebrow: 'STEP 4 · 房间里的其他角落',
      title: '使用导航切换页面',
      body: '明信片用于查看生成结果，发现用于浏览公开来信，信箱用于与其他用户通信，记忆本用于保存个人片段。',
    },
  ];

  let active = false;
  let automaticOwner = null;
  let index = 0;
  let root = null;
  let spotlight = null;
  let panel = null;
  let previousFocus = null;
  let repositionFrame = 0;

  function isPending() {
    return App.state.onboardingVersion === 0 || App.state.onboardingVersion === '0';
  }

  function maybeStart() {
    if (active || !Auth.isLoggedIn()) return;
    const user = Auth.getUser();
    const owner = String(user?.id || user?.username || 'authenticated');
    if (automaticOwner === owner) return;
    automaticOwner = owner;
    if (!isPending()) return;
    window.setTimeout(() => start(), 240);
  }

  function start({ force = false } = {}) {
    if (active) return;
    if (!force && !isPending()) return;
    active = true;
    index = 0;
    previousFocus = document.activeElement;
    build();
    document.addEventListener('keydown', onKeydown);
    window.addEventListener('resize', schedulePosition);
    document.getElementById('workspace-content')?.addEventListener('scroll', schedulePosition, { passive: true });
    showStep();
  }

  function build() {
    root = document.createElement('div');
    root.className = 'onboarding-tour';
    root.innerHTML = `
      <div class="onboarding-backdrop" aria-hidden="true"></div>
      <div class="onboarding-spotlight" aria-hidden="true"></div>
      <section class="onboarding-card" role="dialog" aria-modal="true" aria-labelledby="onboarding-title" aria-describedby="onboarding-body">
        <button class="onboarding-skip" type="button" data-action="skip">跳过引导</button>
        <span class="onboarding-kicker"></span>
        <h2 id="onboarding-title"></h2>
        <p id="onboarding-body"></p>
        <div class="onboarding-progress" aria-label="引导进度"></div>
        <div class="onboarding-actions">
          <button class="btn btn-sec" type="button" data-action="back">上一步</button>
          <button class="btn btn-pri" type="button" data-action="next">下一步</button>
        </div>
      </section>`;
    document.body.appendChild(root);
    spotlight = root.querySelector('.onboarding-spotlight');
    panel = root.querySelector('.onboarding-card');
    root.querySelector('[data-action="skip"]').addEventListener('click', () => close(true));
    root.querySelector('[data-action="back"]').addEventListener('click', previous);
    root.querySelector('[data-action="next"]').addEventListener('click', next);
  }

  async function showStep() {
    if (!active) return;
    const step = steps[index];
    if (App.currentPage !== step.page) App.navigate(step.page);

    panel.querySelector('.onboarding-kicker').textContent = step.eyebrow;
    panel.querySelector('h2').textContent = step.title;
    panel.querySelector('p').textContent = step.body;
    panel.querySelector('[data-action="back"]').hidden = index === 0;
    const nextButton = panel.querySelector('[data-action="next"]');
    nextButton.textContent = index === steps.length - 1 ? '开始写第一封信' : '下一步';
    panel.querySelector('.onboarding-progress').innerHTML = steps.map((_, stepIndex) =>
      `<span class="${stepIndex === index ? 'active' : ''}" aria-label="第 ${stepIndex + 1} 步"></span>`
    ).join('');

    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)));
    const target = document.querySelector(step.selector);
    if (target && !isFixedNavigation(target)) {
      target.scrollIntoView({ behavior: prefersReducedMotion() ? 'auto' : 'smooth', block: 'center', inline: 'nearest' });
      await new Promise(resolve => window.setTimeout(resolve, prefersReducedMotion() ? 0 : 180));
    }
    position(target);
    panel.querySelector('[data-action="next"]').focus({ preventScroll: true });
  }

  function isFixedNavigation(target) {
    return target?.matches('.rail-nav') && window.matchMedia('(max-width: 1023px)').matches;
  }

  function position(target = document.querySelector(steps[index]?.selector)) {
    if (!active || !panel || !spotlight) return;
    const rect = target?.getBoundingClientRect();
    const visible = rect && rect.width > 0 && rect.height > 0 &&
      rect.bottom > 0 && rect.top < window.innerHeight && rect.right > 0 && rect.left < window.innerWidth;

    spotlight.classList.toggle('is-hidden', !visible);
    panel.classList.toggle('is-centered', !visible);
    panel.style.removeProperty('top');
    panel.style.removeProperty('left');
    panel.style.removeProperty('right');
    panel.style.removeProperty('bottom');

    if (!visible) return;
    const padding = 9;
    spotlight.style.top = `${Math.max(6, rect.top - padding)}px`;
    spotlight.style.left = `${Math.max(6, rect.left - padding)}px`;
    spotlight.style.width = `${Math.min(window.innerWidth - 12, rect.width + padding * 2)}px`;
    spotlight.style.height = `${Math.min(window.innerHeight - 12, rect.height + padding * 2)}px`;

    if (window.matchMedia('(max-width: 767px)').matches) return;
    const panelWidth = Math.min(410, window.innerWidth - 36);
    const panelHeight = panel.offsetHeight || 280;
    const gap = 22;
    const rightSpace = window.innerWidth - rect.right;
    const leftSpace = rect.left;
    const belowSpace = window.innerHeight - rect.bottom;
    const aboveSpace = rect.top;
    let left;
    let top;
    if (rightSpace >= panelWidth + gap) {
      left = rect.right + gap;
      top = rect.top;
    } else if (leftSpace >= panelWidth + gap) {
      left = rect.left - panelWidth - gap;
      top = rect.top;
    } else if (belowSpace >= panelHeight + gap) {
      left = rect.left + (rect.width - panelWidth) / 2;
      top = rect.bottom + gap;
    } else if (aboveSpace >= panelHeight + gap) {
      left = rect.left + (rect.width - panelWidth) / 2;
      top = rect.top - panelHeight - gap;
    } else {
      left = rect.left + (rect.width - panelWidth) / 2;
      top = window.innerHeight - panelHeight - 18;
    }
    if (top + panelHeight > window.innerHeight - 18) top = window.innerHeight - panelHeight - 18;
    panel.style.left = `${Math.max(18, left)}px`;
    panel.style.top = `${Math.max(18, top)}px`;
  }

  function schedulePosition() {
    cancelAnimationFrame(repositionFrame);
    repositionFrame = requestAnimationFrame(() => position());
  }

  function prefersReducedMotion() {
    return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }

  function previous() {
    if (index <= 0) return;
    index -= 1;
    showStep();
  }

  function next() {
    if (index >= steps.length - 1) {
      App.navigate('write_letter');
      close(true);
      return;
    }
    index += 1;
    showStep();
  }

  function onKeydown(event) {
    if (!active) return;
    if (event.key === 'Escape') {
      event.preventDefault();
      close(true);
      return;
    }
    if (event.key !== 'Tab') return;
    const focusable = [...root.querySelectorAll('button:not([hidden]):not(:disabled)')];
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function close(markComplete = false) {
    if (!active) return;
    active = false;
    cancelAnimationFrame(repositionFrame);
    document.removeEventListener('keydown', onKeydown);
    window.removeEventListener('resize', schedulePosition);
    document.getElementById('workspace-content')?.removeEventListener('scroll', schedulePosition);
    root?.remove();
    root = spotlight = panel = null;
    previousFocus?.focus?.({ preventScroll: true });
    previousFocus = null;

    if (!markComplete || !Auth.isLoggedIn()) return;
    try {
      const response = await api.setOnboardingVersion(VERSION);
      if (!response.ok) throw new Error(response.error || '引导状态保存失败');
      App.state.onboardingVersion = VERSION;
    } catch (error) {
      App.showToast('引导已经关闭，但完成状态暂未保存；下次登录还会再次出现。', 4200);
      console.warn('[onboarding] 无法保存完成状态', error);
    }
  }

  return { VERSION, maybeStart, start, close };
})();

window.Onboarding = Onboarding;
