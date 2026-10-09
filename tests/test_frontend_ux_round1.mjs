import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';

const BASE_JS_PATH = process.env.BASE_JS_PATH || 'static/js/base.js';
const baseSource = readFileSync(BASE_JS_PATH, 'utf8');

function extractSection(src, startMarker, endMarker) {
  const s = src.indexOf(startMarker);
  if (s < 0) throw new Error('section start not found: ' + startMarker);
  const e = src.indexOf(endMarker, s);
  if (e < 0) throw new Error('section end not found: ' + endMarker);
  return src.slice(s, e);
}

function createEl(tag, attrs = {}) {
  const el = {
    tagName: tag,
    _attrs: { ...attrs },
    dataset: {},
    children: [],
    parentElement: null,
    disabled: false,
    title: '',
    style: {},
    textContent: '',
    value: '',
    classList: (() => {
      const set = new Set((attrs.class || '').split(/\s+/).filter(Boolean));
      return {
        add: (...c) => c.forEach(x => set.add(x)),
        remove: (...c) => c.forEach(x => set.delete(x)),
        contains: c => set.has(c),
        toggle: (c, force) => {
          const has = set.has(c);
          const want = force === undefined ? !has : !!force;
          if (want) set.add(c); else set.delete(c);
          return want;
        },
        _set: set,
      };
    })(),
    getAttribute(name) {
      if (name in this.dataset && name.startsWith('data-')) return this.dataset[name.slice(5)];
      return name in this._attrs ? String(this._attrs[name]) : null;
    },
    setAttribute(name, val) {
      if (name in this.dataset && name.startsWith('data-')) this.dataset[name.slice(5)] = String(val);
      else this._attrs[name] = String(val);
    },
    removeAttribute(name) { delete this._attrs[name]; },
    appendChild(child) { child.parentElement = this; this.children.push(child); return child; },
    querySelector(sel) {
      for (const c of this.children) {
        if (matchesSimple(c, sel)) return c;
        const d = c.querySelector(sel);
        if (d) return d;
      }
      return null;
    },
    querySelectorAll(sel) {
      const out = [];
      for (const c of this.children) {
        if (matchesSimple(c, sel)) out.push(c);
        out.push(...c.querySelectorAll(sel));
      }
      return out;
    },
    addEventListener(type, fn) { (this._listeners ||= {})[type] = fn; },
    dispatchEvent(ev) {
      const fn = this._listeners?.[ev.type];
      if (fn) fn.call(this, ev);
      return true;
    },
  };
  return el;
}

function matchesSimple(el, sel) {
  if (!sel) return false;

  // Handle attribute selectors FIRST (before plain .class)
  if (sel.includes('[') && sel.endsWith(']')) {
    const m = sel.match(/^(\.?[\w-]+)?\[([^=\]]+)(?:=['"]?([^'"\]]*)['"]?)?\]$/);
    if (!m) return false;
    const [, clsPart, attr, val] = m;
    const cls = clsPart ? clsPart.replace(/^\./, '') : null;
    if (cls) {
      const actual = String(el.className || '');
      const inSet = new Set(actual.split(/\s+/).filter(Boolean));
      const listContains = el.classList && typeof el.classList.contains === 'function'
        ? el.classList.contains(cls)
        : false;
      if (!inSet.has(cls) && !listContains) return false;
    }
    if (attr === 'data-isbn') {
      const have = el.getAttribute ? el.getAttribute('data-isbn') : undefined;
      return val === undefined ? have != null : have === val;
    }
    return false;
  }

  // Plain class selector: match against ACTUAL className string OR classList.contains.
  // The Analytics renderer assigns node.className='panel-status' directly without
  // updating the mock classList Set, so classList alone is not authoritative here.
  if (sel.startsWith('.')) {
    const cls = sel.slice(1);
    const actual = String(el.className || '');
    const inSet = new Set(actual.split(/\s+/).filter(Boolean));
    const listContains = el.classList && typeof el.classList.contains === 'function'
      ? el.classList.contains(cls)
      : false;
    return inSet.has(cls) || listContains;
  }

  return String(el.tagName || '').toLowerCase() === sel.toLowerCase();
}

function makeDoc(buttons = []) {
  const root = createEl('body');
  buttons.forEach(b => root.appendChild(b));
  const doc = {
    readyState: 'complete',
    documentElement: createEl('html'),
    body: root,
    getElementById(id) { return root.querySelector('#' + id); },
    querySelector(sel) { return root.querySelector(sel); },
    querySelectorAll(sel) {
      const all = root.querySelectorAll(sel);
      if (sel === '.btn-favorite[data-isbn]') return all.filter(b => b.classList.contains('btn-favorite') && b.getAttribute('data-isbn') !== null);
      if (sel === '.btn-favorite') return all.filter(b => b.classList.contains('btn-favorite'));
      if (sel === '[data-favorite-count]') return all.filter(b => b.classList.contains('favorite-count'));
      if (sel === 'use') return all.filter(b => b.tagName.toLowerCase() === 'use');
      return all;
    },
    createElement(tag) { return createEl(tag); },
    addEventListener() {},
  };
  return doc;
}

function favButton(isbn, active = false) {
  const btn = createEl('button', { class: 'btn-favorite' + (active ? ' active' : ''), 'data-isbn': isbn });
  btn.setAttribute('aria-pressed', active ? 'true' : 'false');
  const use = createEl('use', { href: active ? '#icon-heart-filled' : '#icon-heart' });
  btn.appendChild(use);
  return btn;
}

function deferred(resolver) {
  let resolveFn, rejectFn;
  const promise = new Promise((res, rej) => { resolveFn = res; rejectFn = rej; });
  resolver(resolveFn, rejectFn);
  return promise;
}

function flushPromises() {
  return new Promise(r => setTimeout(r, 0));
}

function loadFavoritesVM({ buttons = [], fetchImpl, lang = 'zh', countEl = null } = {}) {
  const section = extractSection(baseSource, '// ===== Favorite Functions =====', '// ===== Filter Functions =====');
  const sandbox = {};
  const ctx = vm.createContext(sandbox);
  const code = section + `
;(function(){
  Object.assign(__api, { normalizeIsbn: typeof normalizeIsbn === 'function' ? normalizeIsbn : undefined, getFavoriteLabel: typeof getFavoriteLabel === 'function' ? getFavoriteLabel : undefined, toggleFavorite, hydrateFavorites: typeof hydrateFavorites === 'function' ? hydrateFavorites : undefined });
})();`;
  const doc = makeDoc([...buttons, ...(countEl ? [countEl] : [])]);
  const toasts = [];
  const timers = [];
  const api = {};
  Object.assign(sandbox, {
    __api: api,
    console,
    WeakSet,
    Promise,
    setTimeout: (fn, ms) => { timers.push({ fn, ms }); return timers.length; },
    clearTimeout: () => {},
    fetch: fetchImpl,
    document: doc,
    window: { t: undefined },
    navigator: { language: lang === 'en' ? 'en-US' : 'zh-CN' },
    getCurrentLang: () => lang,
    showToast: (msg, type) => toasts.push({ msg, type }),
  });
  vm.runInContext(code, ctx);
  return { api, doc, toasts, timers, ctx, sandbox };
}test('normalizeIsbn accepts hyphenated/spaced ISBNs and rejects garbage', () => {
  const { api } = loadFavoritesVM({});
  assert.equal(api.normalizeIsbn('978-0-306-40615-7'), '9780306406157');
  assert.equal(api.normalizeIsbn(' 0-306-40615-X '), '030640615X');
  assert.equal(api.normalizeIsbn('12345'), null);
  assert.equal(api.normalizeIsbn(''), null);
  assert.equal(api.normalizeIsbn(null), null);
});

test('valid hyphen ISBN sent normalized via POST with correct contract', async () => {
  const btn = favButton('978-0-306-40615-7');
  let captured;
  const fetchImpl = (url, opts) => {
    captured = { url, opts };
    return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ success: true, data: { id: 1, isbn: '9780306406157', created_at: 'now' } }) });
  };
  const { api } = loadFavoritesVM({ buttons: [btn], fetchImpl });
  api.toggleFavorite(btn, '978-0-306-40615-7');
  await flushPromises();
  assert.equal(captured.url, '/api/favorites');
  assert.equal(captured.opts.method, 'POST');
  assert.deepEqual(JSON.parse(captured.opts.body), { isbn: '9780306406157' });
  assert.ok(btn.classList.contains('active'));
  assert.equal(btn.getAttribute('aria-pressed'), 'true');
  assert.equal(btn.querySelector('use').getAttribute('href'), '#icon-heart-filled');
});

test('numeric award ID / malformed input disables button and sends no request', async () => {
  const btn = favButton('12345');
  let called = false;
  const fetchImpl = () => { called = true; return Promise.resolve({ ok: true, json: () => Promise.resolve({}) }); };
  const { api, toasts } = loadFavoritesVM({ buttons: [btn], fetchImpl });
  api.toggleFavorite(btn, '12345');
  await flushPromises();
  assert.equal(called, false);
  assert.equal(btn.disabled, true);
  assert.ok(toasts.some(t => t.type === 'error'));
});

test('same ISBN double click during pending issues only one POST and peers disabled', async () => {
  const a = favButton('9780306406157');
  const b = favButton('978-0-306-40615-7');
  let postCount = 0;
  let resolveFirst;
  const fetchImpl = (url, opts) => {
    if (opts.method === 'POST') postCount++;
    return deferred((res) => { resolveFirst = res; });
  };
  const { api } = loadFavoritesVM({ buttons: [a, b], fetchImpl });
  api.toggleFavorite(a, '9780306406157');
  await flushPromises();
  assert.equal(postCount, 1);
  assert.equal(a.disabled, true);
  assert.equal(b.disabled, true);
  api.toggleFavorite(b, '9780306406157');
  await flushPromises();
  assert.equal(postCount, 1, 'second click must not fire another POST while pending');
  resolveFirst({ ok: true, status: 201, json: () => Promise.resolve({ success: true, data: { id: 1, isbn: '9780306406157' } }) });
  await flushPromises();
  assert.equal(a.disabled, false);
  assert.equal(b.disabled, false);
});

test('HTTP 500 leaves active/icon/aria unchanged then retry works', async () => {
  const btn = favButton('9780306406157');
  let attempt = 0;
  const fetchImpl = () => {
    attempt++;
    if (attempt === 1) return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ success: true, data: {id: 1, isbn: '9780306406157'} }) });
    return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ success: true, data: { id: 1, isbn: '9780306406157' } }) });
  };
  const { api, toasts } = loadFavoritesVM({ buttons: [btn], fetchImpl });
  api.toggleFavorite(btn, '9780306406157');
  await flushPromises();
  assert.ok(!btn.classList.contains('active'), 'must stay inactive after 500');
  assert.equal(btn.getAttribute('aria-pressed'), 'false');
  assert.equal(btn.querySelector('use').getAttribute('href'), '#icon-heart');
  assert.ok(toasts.some(t => t.type === 'error'));
  api.toggleFavorite(btn, '9780306406157');
  await flushPromises();
  assert.ok(btn.classList.contains('active'), 'retry succeeds');
});

test('successful DELETE synchronizes peers and aria', async () => {
  const a = favButton('9780306406157', true);
  const b = favButton('978-0-306-40615-7', true);
  let captured;
  const fetchImpl = (url, opts) => {
    captured = { url, method: opts.method };
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, message: 'removed' }) });
  };
  const { api } = loadFavoritesVM({ buttons: [a, b], fetchImpl });
  api.toggleFavorite(a, '9780306406157');
  await flushPromises();
  assert.equal(captured.method, 'DELETE');
  assert.equal(captured.url, '/api/favorites/9780306406157');
  assert.ok(!a.classList.contains('active'));
  assert.ok(!b.classList.contains('active'));
  assert.equal(a.getAttribute('aria-pressed'), 'false');
  assert.equal(b.getAttribute('aria-pressed'), 'false');
  assert.equal(b.querySelector('use').getAttribute('href'), '#icon-heart');
});

test('hydrate GET runs once and no buttons means no GET', async () => {
  let getCount = 0;
  const fetchImpl = () => {
    getCount++;
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { favorites: [{ isbn: '9780306406157' }], total: 1 } }) });
  };
  const { api } = loadFavoritesVM({ buttons: [], fetchImpl });
  api.hydrateFavorites();
  await flushPromises();
  assert.equal(getCount, 0, 'no .btn-favorite -> no GET');

  const btn = favButton('9780306406157');
  const h2 = loadFavoritesVM({ buttons: [btn], fetchImpl });
  h2.api.hydrateFavorites();
  h2.api.hydrateFavorites();
  await flushPromises();
  assert.equal(getCount, 1, 'hydrate fires exactly one GET');
  assert.ok(btn.classList.contains('active'));
  assert.equal(btn.getAttribute('aria-pressed'), 'true');
});

test('delayed empty GET after direct toggle must not clobber local active peer', async () => {
  const btn = favButton('9780306406157');
  let resolveGet;
  const fetchImpl = (url, opts) => {
    if (opts.method === 'GET') return deferred((res) => { resolveGet = res; });
    return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ success: true, data: { id: 1, isbn: '9780306406157' } }) });
  };
  const { api } = loadFavoritesVM({ buttons: [btn], fetchImpl });
  api.hydrateFavorites(); // starts slow GET
  api.toggleFavorite(btn, '9780306406157'); // direct add completes
  await flushPromises();
  assert.ok(btn.classList.contains('active'), 'direct toggle marks active');
  resolveGet({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { favorites: [], total: 0 } }) });
  await flushPromises();
  assert.ok(btn.classList.contains('active'), 'stale empty hydration must not clobber touched button');
});

test('index loaded after favorite VM does not override API favorite (toggleFavorite wired)', async () => {
  const btn = favButton('9780306406157');
  const fetchCalls = [];
  let storageWrites = 0;
  const stored = {};
  const fetchImpl = (url, opts) => {
    fetchCalls.push({ url, method: opts?.method || 'GET' });
    if (opts?.method === 'POST') {
      // First POST fails; retry POST succeeds. Both go through the real helper path.
      const postCount = fetchCalls.filter(c => c.method === 'POST').length;
      if (postCount === 1) {
        return Promise.resolve({ ok: false, status: 500, json: () => Promise.resolve({ success: false }) });
      }
      return Promise.resolve({ ok: true, status: 201, json: () => Promise.resolve({ success: true, data: { id: 1, isbn: '9780306406157' } }) });
    }
    return Promise.resolve({ ok: true, status: 200, json: () => Promise.resolve({ success: true, data: { favorites: [], total: 0 } }) });
  };
  const { api, ctx } = loadFavoritesVM({ buttons: [btn], fetchImpl });

  // Expose original API favorite onto window BEFORE loading index
  const sandbox = vm.runInContext('this', ctx);
  sandbox.window = sandbox.window || {};
  sandbox.window.toggleFavorite = api.toggleFavorite;
  sandbox.window.addEventListener = () => {};
  sandbox.window.APP_CONFIG = {};
  // Whole-page initialization also reads standard browser URL context.
  sandbox.URLSearchParams = URLSearchParams;
  sandbox.window.location = { search: '', pathname: '/' };

  // localStorage mock MUST be assigned before the source runs so any init-time
  // read/write hits it. getItem returns null (no cached favorites), setItem tracks writes.
  sandbox.localStorage = {
    getItem(k) { return k in stored ? stored[k] : null; },
    setItem(k, v) { storageWrites++; stored[k] = String(v); },
    removeItem(k) { delete stored[k]; },
    clear() {},
  };
  sandbox.sessionStorage = {
    getItem() { return null; },
    setItem() {},
    removeItem() {},
    clear() {},
  };

  // Load ACTUAL static/js/index.js whole with DOM globals/mocks needed
  const indexSrc = readFileSync(process.env.INDEX_JS_PATH || 'static/js/index.js', 'utf8');
  vm.runInContext(indexSrc, ctx);

  // Build a realistic card containing the favorite button
  const card = createEl('div', { class: 'book-card', 'data-isbn': '9780306406157' });
  card.appendChild(btn);

  // Call real handleCardClick with target.closest returning clicked favorite
  const clickEvent = {
    target: {
      closest: (sel) => {
        if (sel === '.btn-favorite') return btn;
        if (sel === '.book-card') return card;
        return null;
      }
    },
    stopPropagation: () => {}
  };

  // Find and invoke the actual handleCardClick from loaded index source
  const handleCardClickFn = vm.runInContext(
    '(typeof handleCardClick === "function") ? handleCardClick : null',
    ctx
  );
  assert.ok(handleCardClickFn, 'handleCardClick must exist in index.js');

  // Simulate click routing through the real handler (first POST -> failure)
  handleCardClickFn(clickEvent);
  await flushPromises();

  assert.equal(btn.classList.contains('active'), false, 'index API failure retains inactive state');
  assert.equal(btn.getAttribute('aria-pressed'), 'false');
  assert.equal(btn.querySelector('use').getAttribute('href'), '#icon-heart');
  assert.equal(btn.disabled, false);

  // Retry via the same real helper path (second POST -> success)
  handleCardClickFn(clickEvent);
  await flushPromises();

  assert.equal(storageWrites, 0, 'index must not write localStorage favorites');
  assert.ok(fetchCalls.some(c => c.method === 'POST' && c.url.includes('/api/favorites')), 'API POST request made for favorite');
  assert.ok(fetchCalls.some(c => c.method === 'POST'), 'retry POST issued after first failure');
  assert.ok(btn.classList.contains('active'), 'API favorite path applied active state after retry');
});// ---------------- Intro tests (desktop + mobile) ----------------

function runIntroScript(source, { descId, btnId, wrapperId, collapsedClass, lang = 'zh', longText = true } = {}) {
  const mobile = descId === 'm-desc-content';
  const desc = createEl(mobile ? 'div' : 'p', {id: descId});
  const btn = createEl('button', {id: btnId, 'aria-expanded':'false'});
  const wrapper = createEl('div', {id: wrapperId});
  wrapper.appendChild(desc); wrapper.appendChild(btn);
  desc.textContent = longText ? 'x'.repeat(200) : 'short';
  desc.scrollHeight = longText ? 200 : 50;
  const clamp = mobile ? desc : wrapper;
  clamp.classList.add(collapsedClass);
  Object.defineProperty(desc, 'clientHeight', {get: () => longText ? (clamp.classList.contains(collapsedClass) ? 100 : 200) : 50});
  const doc = makeDoc([wrapper]);
  doc.getElementById = id => id === descId ? desc : id === btnId ? btn : id === wrapperId ? wrapper : null;
  const frames=[], winListeners={};
  const sandbox={document:doc, navigator:{language:lang}, window:{__APP_LANG__:lang, addEventListener:(type, fn) => (winListeners[type] ||= []).push(fn)}, requestAnimationFrame:fn => frames.push(fn)};
  vm.runInNewContext(source,sandbox);
  const flushRaf=() => { const batch=frames.splice(0); batch.forEach(fn=>fn()); };
  return {desc,btn,wrapper,flushRaf,winListeners,sandbox};
}

function desktopIntroSource() {
  const tplPath = process.env.DESKTOP_TPL_PATH || 'templates/new_book_detail.html';
  const html = readFileSync(tplPath, 'utf8');
  // Anchor on the exact JS line inside the IIFE, NOT the first HTML occurrence of
  // 'detail-description-wrapper' (which sits outside the script and yields no enclosing IIFE).
  const marker = "const wrapper = document.getElementById('detail-description-wrapper')";
  const markerIdx = html.indexOf(marker);
  if (markerIdx < 0) throw new Error('desktop intro IIFE marker not found');
  // Walk back to find the enclosing (function() {
  const funcStart = html.lastIndexOf('(function()', markerIdx);
  if (funcStart < 0) throw new Error('desktop intro IIFE start not found');
  // Find end: next })(); after the marker
  const endMarker = '})();';
  const funcEnd = html.indexOf(endMarker, markerIdx);
  if (funcEnd < 0) throw new Error('desktop intro IIFE end not found');
  return html.slice(funcStart, funcEnd + endMarker.length);
}function mobileIntroSource() {
  const tplPath = process.env.MOBILE_TPL_PATH || 'templates/mobile/new_book_detail.html';
  const html = readFileSync(tplPath, 'utf8');
  // nonce regex must permit Jinja quote string
  const scriptMatch = html.match(/<script\s+nonce="[^"]*">([\s\S]*?)<\/script>/);
  if (!scriptMatch) throw new Error('mobile intro script not found');
  // Replace '{{ _l }}' with zh for test execution
  return scriptMatch[1].replace(/\{\{\s*_l\s*\}\}/g, 'zh');
}

test('desktop intro: long text shows button, expand/collapse preserves content, resize/lang preserves expanded+English Show less, short hides', () => {
  const src = desktopIntroSource();

  // Long text scenario
  const long = runIntroScript(src, {
    descId: 'detail-description',
    btnId: 'toggle-detail-description',
    wrapperId: 'detail-description-wrapper',
    collapsedClass: 'is-collapsed',
    longText: true,
    lang: 'zh',
  });
  long.flushRaf();
  assert.notEqual(long.btn.style.display, 'none', 'button visible for overflowing text');

  // Click to expand
  long.btn.dispatchEvent({ type: 'click' });
  const before = long.desc.textContent;
  assert.equal(long.btn.getAttribute('aria-expanded'), 'true', 'expanded after click');
  assert.equal(long.desc.textContent, before, 'full text unchanged on expand');

  // Resize preserves expanded + English label
  const resizeFns = long.winListeners['resize'] || [];
  resizeFns.forEach(fn => fn());
  long.flushRaf();
  assert.equal(long.btn.getAttribute('aria-expanded'), 'true', 'expanded preserved across resize');

  // Language change to en while expanded → Show less
  const langFns = long.winListeners['languagechange'] || [];
  langFns.forEach(fn => fn({ detail: { language: 'en' } }));
  long.flushRaf();
  assert.equal(long.btn.getAttribute('aria-expanded'), 'true', 'expanded preserved across lang change');
  assert.match(long.btn.textContent, /Show less/, 'English label shows Show less when expanded');

  // Click to collapse
  long.btn.dispatchEvent({ type: 'click' });
  assert.equal(long.btn.getAttribute('aria-expanded'), 'false', 'collapsed after second click');

  // Short text scenario: button hidden
  const short = runIntroScript(src, {
    descId: 'detail-description',
    btnId: 'toggle-detail-description',
    wrapperId: 'detail-description-wrapper',
    collapsedClass: 'is-collapsed',
    longText: false,
    lang: 'zh',
  });
  short.flushRaf();
  assert.equal(short.btn.style.display, 'none', 'short text hides toggle button');
});

test('mobile intro: long text shows button, expand/collapse preserves content, resize/lang preserves expanded+English Show less, short hides', () => {
  const src = mobileIntroSource();

  // Long text scenario
  const long = runIntroScript(src, {
    descId: 'm-desc-content',
    btnId: 'm-desc-toggle',
    wrapperId: 'm-desc-content',
    collapsedClass: 'm-desc-collapsed',
    longText: true,
    lang: 'zh',
  });
  long.flushRaf();
  assert.notEqual(long.btn.style.display, 'none', 'button visible for overflowing text');

  // Click to expand
  long.btn.dispatchEvent({ type: 'click' });
  const before = long.desc.textContent;
  assert.equal(long.btn.getAttribute('aria-expanded'), 'true', 'expanded after click');
  assert.equal(long.desc.textContent, before, 'full text unchanged on expand');

  // Resize preserves expanded
  const resizeFns = long.winListeners['resize'] || [];
  resizeFns.forEach(fn => fn());
  assert.equal(long.btn.getAttribute('aria-expanded'), 'true', 'expanded preserved across resize');

  // Language change to en while expanded → Show less
  const langFns = long.winListeners['languagechange'] || [];
  langFns.forEach(fn => fn({ detail: { language: 'en-US' } }));
  assert.equal(long.btn.getAttribute('aria-expanded'), 'true', 'expanded preserved across lang change');
  assert.match(long.btn.textContent, /Show less/, 'English label shows Show less when expanded');

  // Click to collapse
  long.btn.dispatchEvent({ type: 'click' });
  assert.equal(long.btn.getAttribute('aria-expanded'), 'false', 'collapsed after second click');

  // Short text scenario: button hidden
  const short = runIntroScript(src, {
    descId: 'm-desc-content',
    btnId: 'm-desc-toggle',
    wrapperId: 'm-desc-content',
    collapsedClass: 'm-desc-collapsed',
    longText: false,
    lang: 'zh',
  });
  short.flushRaf();
  assert.equal(short.btn.style.display, 'none', 'short text hides toggle button');
});// ---------------- Static contracts ----------------

test('awards template renders favorite button keyed by ISBN not book.id', () => {
  const tpl = readFileSync(process.env.AWARDS_TPL_PATH || 'templates/awards.html', 'utf8');
  // Actual data-isbn uses Jinja local variable isbn
  assert.match(tpl, /data-isbn="\{\{[^}]*isbn/i, 'favorite button must carry ISBN via Jinja variable');
});

test('weekly report inline CSS has dedicated modal classes, fixed overlay + internal scroll, no generic modal classes', () => {
  // Source is ONLY templates/weekly_report_detail.html INLINE CSS; there is no
  // static/css/weekly_report.css file to read.
  const tpl = readFileSync(process.env.WEEKLY_DETAIL_TPL_PATH || 'templates/weekly_report_detail.html', 'utf8');

  // Dedicated overlay / panel / body definitions must exist.
  assert.match(tpl, /\.weekly-modal-overlay\b/, 'dedicated .weekly-modal-overlay definition required');
  assert.match(tpl, /\.weekly-modal-panel\b/, 'dedicated .weekly-modal-panel definition required');
  assert.match(tpl, /\.weekly-modal-body\b/, 'dedicated .weekly-modal-body definition required');

  // Overlay is fixed-positioned; body scrolls internally.
  assert.match(tpl, /\.weekly-modal-overlay[^{}]*\{[^}]*position:\s*fixed/, 'overlay is fixed');
  assert.match(tpl, /\.weekly-modal-body[^{}]*\{[^}]*overflow(-y)?:\s*(auto|scroll)/, 'internal body scrolls');

  // No generic .modal-content / .modal-overlay classes anywhere.
  assert.doesNotMatch(tpl, /\.modal-content\b/, 'no generic .modal-content class');
  assert.doesNotMatch(tpl, /\.modal-overlay\b/, 'no generic .modal-overlay class');
});
// Analytics: execute the standalone template script with real table/tbody structure.
function analyticsFixture() {
  const nodes = new Map();
  const created = [];
  const matches = (node, selector) => selector.startsWith('.')
    ? (node.className || '').split(/\s+/).includes(selector.slice(1))
    : node.tagName === selector.toUpperCase();
  function el(tag, id = '') {
    const node = {
      tagName: tag.toUpperCase(), id, className: '', style: {}, children: [], dataset: {},
      parentElement: null, parentNode: null, listeners: {}, attrs: {}, disabled: false,
      get textContent() { return this.children.length ? this.children.map(x => x.textContent).join('') : (this.text || ''); },
      set textContent(value) { this.children = []; this.text = String(value); },
      get firstChild() { return this.children[0] || null; },
      appendChild(child) {
        assert(!(this.tagName === 'TABLE' || this.tagName === 'TBODY') || child.tagName !== 'DIV', 'status must be outside table');
        child.parentElement = child.parentNode = this; this.children.push(child); return child;
      },
      removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
      setAttribute(name, value) { this.attrs[name] = String(value); },
      closest(selector) { for (let n = this; n; n = n.parentElement) if (matches(n, selector)) return n; return null; },
      querySelector(selector) {
        const direct = selector.startsWith(':scope > ');
        if (direct) selector = selector.slice(9);
        for (const child of this.children) {
          if (!child.tagName) continue;
          if (matches(child, selector)) return child;
          if (!direct) { const found = child.querySelector(selector); if (found) return found; }
        }
        return null;
      },
      addEventListener(type, fn) { this.listeners[type] = fn; },
      getContext() { return {}; },
    };
    Object.defineProperty(node, 'innerHTML', { set() { throw new Error('unsafe innerHTML'); } });
    created.push(node);
    if (id) nodes.set(id, node);
    return node;
  }
  const card = () => { const n = el('div'); n.className = 'card-body'; return n; };
  for (const id of ['viewsChart', 'behaviorChart', 'dailyChart']) card().appendChild(el('canvas', id));
  const tableCard = card(); const table = tableCard.appendChild(el('table'));
  table.appendChild(el('tbody', 'top-reports-table'));
  card().appendChild(el('span', 'session-count'));
  for (const id of ['total-views', 'avg-views', 'total-behaviors']) el('span', id);
  let ready;
  const document = {
    getElementById: id => nodes.get(id), createElement: el,
    querySelectorAll: selector => created.filter(node => matches(node, selector)),
    createTextNode: text => ({ textContent: text }),
    addEventListener: (type, fn) => { if (type === 'DOMContentLoaded') ready = fn; },
  };
  return { nodes, document, start: () => ready(), tableCard };
}
function analyticPayload(url, empty = false) {
  if (url.includes('report-views')) return { success: true, data: { total_views: empty ? 0 : 42, average_views: empty ? 0 : 21, view_stats: empty ? [] : [{ date: 'd', view_count: 42 }] } };
  if (url.includes('user-behavior')) return { success: true, data: { total_behaviors: empty ? 0 : 5, behavior_stats: empty ? [] : [{ event_type: 'click', count: 5 }] } };
  if (url.includes('daily-stats')) return { success: true, data: { daily_stats: empty ? [] : [{ date: 'd', count: 2 }] } };
  if (url.includes('top-reports')) return { success: true, data: empty ? [] : [{ date: '2026-09-30', title: '<img src=x onerror=alert(1)>', view_count: 7 }] };
  if (url.includes('session-stats')) return { success: true, data: { session_count: empty ? 0 : 9 } };
  throw new Error('Unexpected endpoint ' + url);
}
async function analyticsVM(fixture, responder, chartAvailable = true) {
  const html = readFileSync(process.env.ANALYTICS_TPL_PATH || 'templates/analytics_dashboard.html', 'utf8');
  const scripts = [...html.matchAll(/<script\s+nonce="[^"]*">([\s\S]*?)<\/script>/g)];
  const source = scripts.find(m => m[1].includes('chartColors'))?.[1];
  assert(source, 'actual analytics script required');
  const Chart = chartAvailable ? class { destroy() {} } : undefined;
  const ctx = vm.createContext({ document: fixture.document, fetch: responder, Chart, console: { error() {} } });
  vm.runInContext(source, ctx); fixture.start(); await flushPromises();
}
const response = (body, status = 200) => ({ ok: status < 400, status, json: async () => body });
const panelStatus = (f, id) => f.nodes.get(id).parentElement.querySelector('.panel-status');
test('analytics safely renders hostile title as literal text in real tbody', async () => {
  const f = analyticsFixture(); await analyticsVM(f, async url => response(analyticPayload(url)));
  const row = f.nodes.get('top-reports-table').children[0];
  assert.equal(row.children[1].textContent, '<img src=x onerror=alert(1)>');
  assert.equal(row.children[3].children[0].href, '/reports/weekly/2026-09-30?lang=zh');
  assert.equal(f.tableCard.querySelector('.panel-status').textContent, '');
});
test('analytics HTTP failure stays local; retry updates the failed widget', async () => {
  const f = analyticsFixture(); let fail = true;
  await analyticsVM(f, async url => response(analyticPayload(url), fail && url.includes('report-views') ? 500 : 200));
  const status = panelStatus(f, 'viewsChart');
  assert.equal(status.textContent, '加载失败，请重试重试');
  const retry = status.querySelector('button'); assert(retry);
  assert.equal(f.nodes.get('total-behaviors').textContent, '5');
  assert.equal(f.nodes.get('session-count').textContent, '9');
  fail = false; retry.listeners.click(); await flushPromises();
  assert.equal(f.nodes.get('total-views').textContent, '42');
  assert.equal(status.textContent, '');
});
test('analytics empty datasets retain visible no-data states and zero metrics', async () => {
  const f = analyticsFixture(); await analyticsVM(f, async url => response(analyticPayload(url, true)));
  for (const id of ['viewsChart', 'behaviorChart', 'dailyChart']) assert.equal(panelStatus(f, id).textContent, '暂无数据');
  assert.equal(f.nodes.get('top-reports-table').children[0].children[0].textContent, '暂无数据');
  for (const id of ['total-views', 'avg-views', 'total-behaviors', 'session-count']) assert.equal(f.nodes.get(id).textContent, '0');
});
test('analytics absent Chart shows failure + retry while table and sessions succeed', async () => {
  const f = analyticsFixture(); await analyticsVM(f, async url => response(analyticPayload(url)), false);
  for (const id of ['viewsChart', 'behaviorChart', 'dailyChart']) {
    const status = panelStatus(f, id);
    assert.equal(status.textContent, '加载失败，请重试重试'); assert(status.querySelector('button'));
  }
  assert.equal(f.nodes.get('session-count').textContent, '9');
  assert.equal(f.nodes.get('top-reports-table').children[0].children[1].textContent, '<img src=x onerror=alert(1)>');
});

// Mobile: execute actual favorite functions; existing CSRF helper is mocked at its boundary.
function mobileFavoriteVM(buttons = [], handler = async () => response({ success: true, data: { favorites: [], total: 0 } })) {
  const source = readFileSync(process.env.MOBILE_JS_PATH || 'static/mobile/js/mobile.js', 'utf8');
  const section = extractSection(source, '    function normalizeIsbn', '    function initFavoriteRemove');
  const api = {}, calls = [], toasts = [];
  const network = (url, opts = {}) => { calls.push({ url, opts }); return handler(url, opts); };
  const document = {
    documentElement: { getAttribute: () => 'zh' },
    querySelectorAll: selector => selector === '.m-favorite-btn[data-isbn]' ? buttons : [],
  };
  vm.runInNewContext(section + '\nObject.assign(api, {normalizeIsbn, toggleMobileFavorite, initMobileFavorites});',
    { api, document, csrfFetch: network, fetch: network, toast: (msg, type) => toasts.push({ msg, type }), SERVER_LANGUAGE: 'zh' });
  return { api, calls, toasts };
}
function mobileFavButton(isbn, pressed = false) {
  const btn = createEl('button', { class: 'm-favorite-btn', 'data-isbn': isbn, 'aria-pressed': String(pressed) });
  const svg = btn.appendChild(createEl('svg')); const path = svg.appendChild(createEl('path', { fill: pressed ? 'currentColor' : 'none' }));
  return { btn, path };
}
test('mobile invalid ISBN is disabled with explanation and no request', () => {
  const { btn } = mobileFavButton('123'); const h = mobileFavoriteVM([btn]);
  h.api.toggleMobileFavorite(btn);
  assert.equal(btn.disabled, true); assert.equal(btn.getAttribute('aria-label'), 'ISBN无效或缺失，无法收藏'); assert.equal(h.calls.length, 0);
});
test('mobile initial GET runs only with buttons, once, and hydrated button remains clickable', async () => {
  const empty = mobileFavoriteVM(); empty.api.initMobileFavorites(); assert.equal(empty.calls.length, 0);
  const { btn } = mobileFavButton('9780306406157');
  const h = mobileFavoriteVM([btn], async (url, opts) => response(opts.method === 'DELETE'
    ? { success: true, message: 'removed' } : { success: true, data: { favorites: [{ isbn: '9780306406157' }], total: 1 } }));
  h.api.initMobileFavorites(); h.api.initMobileFavorites(); await flushPromises();
  assert.equal(h.calls.length, 1); assert.equal(btn.getAttribute('aria-pressed'), 'true');
  btn.dispatchEvent({ type: 'click', preventDefault() {}, stopPropagation() {} }); await flushPromises();
  assert.equal(h.calls.length, 2); assert.equal(h.calls[1].opts.method, 'DELETE');
  assert.equal(h.calls[1].url, '/api/favorites/9780306406157'); assert.equal(h.calls[1].opts.body, undefined);
  assert.equal(btn.getAttribute('aria-pressed'), 'false');
});
test('mobile duplicate click disables peers and POST obeys real contract', async () => {
  const a = mobileFavButton('9780306406157'), b = mobileFavButton('978-0-306-40615-7');
  let resolvePost; const h = mobileFavoriteVM([a.btn, b.btn], () => new Promise(resolve => { resolvePost = resolve; }));
  h.api.toggleMobileFavorite(a.btn); h.api.toggleMobileFavorite(b.btn);
  assert.equal(h.calls.length, 1); assert(a.btn.disabled && b.btn.disabled);
  assert.equal(h.calls[0].url, '/api/favorites');
  assert.deepEqual(JSON.parse(h.calls[0].opts.body), { isbn: '9780306406157' });
  resolvePost(response({ success: true, data: { id: 1, isbn: '9780306406157', created_at: 'now' } }, 201)); await flushPromises();
  for (const item of [a, b]) { assert.equal(item.btn.getAttribute('aria-pressed'), 'true'); assert.equal(item.path.getAttribute('fill'), 'currentColor'); assert.equal(item.btn.disabled, false); }
});
test('mobile HTTP/API failures leave state and icon unchanged; retry succeeds', async () => {
  for (const bad of [response({ success: true, data: { id: 1, isbn: '9780306406157' } }, 500), response({ success: false })]) {
    const { btn, path } = mobileFavButton('9780306406157'); let fail = true;
    const h = mobileFavoriteVM([btn], async () => fail ? bad : response({ success: true, data: { id: 1, isbn: '9780306406157' } }, 201));
    h.api.toggleMobileFavorite(btn); await flushPromises();
    assert.equal(btn.getAttribute('aria-pressed'), 'false'); assert.equal(path.getAttribute('fill'), 'none'); assert.equal(btn.disabled, false);
    assert.equal(h.toasts[0].type, 'error');
    fail = false; h.api.toggleMobileFavorite(btn); await flushPromises(); assert.equal(btn.getAttribute('aria-pressed'), 'true');
  }
});
test('mobile deferred empty GET cannot overwrite a later successful mutation or peers', async () => {
  const a = mobileFavButton('9780306406157'), b = mobileFavButton('978-0-306-40615-7'); let resolveGet;
  const h = mobileFavoriteVM([a.btn, b.btn], async (url, opts) => opts.method === 'POST'
    ? response({ success: true, data: { id: 1, isbn: '9780306406157' } }, 201)
    : new Promise(resolve => { resolveGet = resolve; }));
  h.api.initMobileFavorites(); h.api.toggleMobileFavorite(a.btn); await flushPromises();
  assert.equal(a.btn.getAttribute('aria-pressed'), 'true');
  resolveGet(response({ success: true, data: { favorites: [], total: 0 } })); await flushPromises();
  for (const btn of [a.btn, b.btn]) assert.equal(btn.getAttribute('aria-pressed'), 'true');
});

// Actual weekly modal open/close handlers: animation-frame focus must not scroll the page.
function weeklyDialogFixture() {
  const source=readFileSync(process.env.WEEKLY_TPL_PATH || 'templates/weekly_report_detail.html','utf8');
  const creation=source.split('\n').find(line=>line.includes('const modalOverlay = document.createElement'));
  assert(creation,'actual dialog creation required');
  const handlers=extractSection(source,'    function openWeeklyModal','    function buildBookDataMap');
  const overlay=createEl('dialog'), close=createEl('button'), body=createEl('div');
  overlay.open=false;let showCalls=0,closeCalls=0,triggerFocuses=0;
  const closeEvents=[];
  const document={body:{style:{overflow:'auto'}},activeElement:null,createElement(tag){assert.equal(tag,'dialog');return overlay;}};
  const trigger={focus(){triggerFocuses++;document.activeElement=trigger;}};
  document.activeElement=trigger;
  close.focus=()=>{if(overlay.open)document.activeElement=close;};
  body.focus=()=>{if(overlay.open)document.activeElement=body;};
  overlay.querySelectorAll=()=>[close,body];
  overlay.showModal=()=>{assert.equal(overlay.open,false);showCalls++;overlay.open=true;close.focus();};
  overlay.close=()=>{assert.equal(overlay.open,true);closeCalls++;overlay.open=false;closeEvents.push(()=>overlay.dispatchEvent({type:'close'}));};
  const ctx=vm.createContext({document,modalClose:close});
  vm.runInContext(creation+'\nlet activeTrigger=null;let oldBodyOverflow="";\n'+handlers,ctx);
  assert.match(source,/<button[^>]*class="weekly-modal-close"[^>]*autofocus/,'native autofocus wiring');
  assert.match(source,/<div class="weekly-modal-body" tabindex="0">/,'keyboard scroll body wiring');
  return {overlay,close,body,document,trigger,
    open:()=>ctx.openWeeklyModal(trigger),teardown:()=>ctx.closeWeeklyModal(),
    flushClose:()=>closeEvents.splice(0).forEach(fn=>fn()),
    calls:()=>({showCalls,closeCalls,triggerFocuses})};
}
test('weekly native dialog enters focus, cancel tears down once, external close cleans up',()=>{
  const f=weeklyDialogFixture();f.open();
  assert.equal(f.overlay.open,true);assert.equal(f.document.activeElement,f.close);assert.equal(f.document.body.style.overflow,'hidden');
  let prevented=false;f.overlay.dispatchEvent({type:'cancel',preventDefault(){prevented=true;}});
  assert.equal(prevented,true);assert.equal(f.overlay.open,false);assert.equal(f.document.body.style.overflow,'auto');assert.equal(f.document.activeElement,f.trigger);
  f.flushClose();assert.deepEqual(f.calls(),{showCalls:1,closeCalls:1,triggerFocuses:1});
  f.open();f.overlay.close();f.flushClose();
  assert.equal(f.overlay.classList.contains('active'),false);assert.equal(f.document.body.style.overflow,'auto');assert.equal(f.document.activeElement,f.trigger);
  assert.equal(f.calls().closeCalls,2);
  // A queued close from the previous opening must not tear down a newly opened dialog.
  f.open();f.teardown();f.open();f.flushClose();
  assert.equal(f.overlay.open,true);assert.equal(f.document.activeElement,f.close);assert.equal(f.document.body.style.overflow,'hidden');
  f.teardown();f.flushClose();assert.equal(f.document.body.style.overflow,'auto');
});
test('weekly actual Tab handler cycles close and scroll body; Escape restores trigger',()=>{
  const f=weeklyDialogFixture();f.open();
  function tab(shift=false){
    const e={type:'keydown',key:'Tab',shiftKey:shift,prevented:false,preventDefault(){this.prevented=true;}};
    f.overlay.dispatchEvent(e);
    if(!e.prevented){(f.document.activeElement===f.close?f.body:f.close).focus();}
  }
  tab();assert.equal(f.document.activeElement,f.body);
  tab();assert.equal(f.document.activeElement,f.close);
  tab(true);assert.equal(f.document.activeElement,f.body);
  f.overlay.dispatchEvent({type:'keydown',key:'Escape'});f.flushClose();
  assert.equal(f.overlay.open,false);assert.equal(f.document.activeElement,f.trigger);assert.equal(f.document.body.style.overflow,'auto');assert.equal(f.calls().closeCalls,1);
});

test('mobile profile remove preserves counts on failure and updates both after confirmed success', async () => {
  const source = readFileSync(process.env.MOBILE_JS_PATH || 'static/mobile/js/mobile.js', 'utf8');
  const section = extractSection(source, '    function normalizeIsbn', '    // ===== 暴露 API =====');
  const count={textContent:'(2)'}, stat={textContent:'已收藏 2 本'}, cards=[{},{}], api={}, toasts=[], calls=[], empty={hidden:true};
  const btn=createEl('button', {'data-isbn':'9780306406157'});
  const card=cards[0]; card.remove=()=>cards.splice(cards.indexOf(card),1); btn.closest=()=>card;
  let click, resolveRequest;
  const document={documentElement:{getAttribute:()=> 'zh'},
    getElementById:id=>id==='m-favorites-empty'?empty:null,
    addEventListener:(type,fn)=>{if(type==='click')click=fn;},
    querySelectorAll:selector=>selector==='#m-favorites .m-book-card'?cards:[],
    querySelector:selector=>selector==='#m-favorites .m-section-count'?count:selector==='.m-profile-stat'?stat:null};
  const csrfFetch=(url,opts)=>{calls.push({url,opts});return new Promise(resolve=>{resolveRequest=resolve;});};
  vm.runInNewContext(section+'\napi.initFavoriteRemove=initFavoriteRemove;', {api,document,csrfFetch,toast:(msg,type)=>toasts.push({msg,type})});
  api.initFavoriteRemove();
  const event={target:{closest:()=>btn},preventDefault(){},stopPropagation(){}};
  click(event); click(event); assert.equal(calls.length,1); assert.equal(btn.disabled,true);
  resolveRequest(response({success:true},500)); await flushPromises();
  assert.equal(cards.length,2); assert.equal(count.textContent,'(2)'); assert.equal(stat.textContent,'已收藏 2 本'); assert.equal(btn.disabled,false); assert.equal(toasts[0].type,'error');
  click(event); assert.equal(calls.length,2); assert.equal(calls[1].url,'/api/favorites/9780306406157'); assert.equal(calls[1].opts.body,undefined);
  resolveRequest(response({success:true,message:'removed'})); await flushPromises();
  assert.equal(cards.length,1); assert.equal(count.textContent,'(1)'); assert.equal(stat.textContent,'已收藏 1 本'); assert.equal(toasts.at(-1).type,'success'); assert.equal(empty.hidden,true,'one favorite remains, reusable empty state stays hidden');
});
