import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';
import test from 'node:test';
import path from 'node:path';
import { spawnSync } from 'node:child_process';

const source = path => fs.readFileSync(path, 'utf8').replace(/\r\n/g, '\n');
const scripts = html => [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(match => match[1]);

class Element {
  constructor(attrs = {}) {
    this.attrs = new Map(Object.entries(attrs)); this.handlers = new Map(); this.children = [];
    this.dataset = {}; this.style = {}; this._text = ''; this.classes = new Set();
    this.classList = { contains: name => this.classes.has(name), add: name => this.classes.add(name), remove: name => this.classes.delete(name), toggle: (name, force) => {
      const on = force === undefined ? !this.classes.has(name) : force;
      if (on) this.classes.add(name); else this.classes.delete(name); return on;
    } };
  }
  getAttribute(name) { return this.attrs.get(name) ?? null; }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  addEventListener(name, callback) { const callbacks = this.handlers.get(name) || []; callbacks.push(callback); this.handlers.set(name, callbacks); }
  fire(name, extra = {}) {
    const event = { target: this, defaultPrevented: false, preventDefault() { this.defaultPrevented = true; }, stopPropagation() {}, ...extra };
    for (const callback of this.handlers.get(name) || []) callback(event); return event;
  }
  appendChild(node) { this.children.push(node); node.parentElement = this; return node; }
  removeChild(node) { this.children.splice(this.children.indexOf(node), 1); }
  get firstChild() { return this.children[0] || null; }
  get textContent() { return this._text + this.children.map(node => node.textContent).join(''); }
  set textContent(value) { this._text = String(value); this.children = []; }
  contains(node) { return node === this || this.children.some(child => child.contains?.(node)); }
  querySelector() { return null; }
  querySelectorAll() { return []; }
}

function languageMenu() {
  const document = new Element(); const globe = new Element({ 'aria-expanded': 'false' }); const dropdown = new Element();
  const buttons = ['zh', 'en'].map(lang => new Element({ 'data-lang': lang, role: 'menuitem' }));
  for (const node of [globe, dropdown, ...buttons]) { node.focus = () => { document.activeElement = node; }; node.click = () => node.fire('click'); }
  buttons.forEach(node => dropdown.appendChild(node)); dropdown.querySelectorAll = selector => selector.includes('button') ? buttons : [];
  document.getElementById = id => ({ 'm-lang-globe': globe, 'm-lang-dropdown': dropdown })[id] || null;
  document.documentElement = new Element(); const window = { location: { href: 'https://bookrank.test/awards?lang=en' } };
  const context = vm.createContext({ document, window, URL, localStorage: { setItem() {} }, setSavedLanguage() {}, getSavedLanguage: () => 'en', applyLanguage() {},
    switchLanguage(lang) { window.location.href = '/set-language?lang=' + lang; } });
  const mobile = source('static/mobile/js/mobile.js'); const start = mobile.indexOf('    function initLangSwitcher()');
  const end = mobile.indexOf('    // ===== 6.', start); assert.ok(start >= 0 && end > start);
  vm.runInContext(mobile.slice(start, end) + '\ninitLangSwitcher();', context);
  function key(target, value) {
    const event = target.fire('keydown', { key: value });
    if (dropdown.contains(target)) dropdown.fire('keydown', { ...event, target });
    document.fire('keydown', { ...event, target });
    if (value === 'Enter' && !event.defaultPrevented) target.click();
  }
  return { document, globe, dropdown, buttons, window, key };
}

test('actual mobile language Escape closes the visible menu, synchronizes expanded state and returns focus', () => {
  const f = languageMenu(); f.globe.click(); f.buttons[1].focus();
  assert.equal(f.dropdown.classList.contains('open'), true); assert.equal(f.globe.getAttribute('aria-expanded'), 'true');
  f.key(f.buttons[1], 'Escape');
  assert.equal(f.dropdown.classList.contains('open'), false); assert.equal(f.globe.getAttribute('aria-expanded'), 'false');
  assert.equal(f.document.activeElement, f.globe);
});

test('actual mobile language keyboard entry, roving selection, native Enter and outside click remain usable', () => {
  const f = languageMenu(); f.globe.focus(); f.key(f.globe, 'ArrowDown');
  assert.equal(f.dropdown.classList.contains('open'), true); assert.equal(f.document.activeElement, f.buttons[0]);
  f.key(f.buttons[0], 'ArrowDown'); assert.equal(f.document.activeElement, f.buttons[1]);
  f.key(f.buttons[1], 'ArrowDown'); assert.equal(f.document.activeElement, f.buttons[0]);
  f.key(f.buttons[0], 'ArrowUp'); assert.equal(f.document.activeElement, f.buttons[1]);
  f.key(f.buttons[1], 'Enter'); assert.equal(f.window.location.href, '/set-language?lang=en');
  assert.equal(f.globe.getAttribute('aria-expanded'), 'false');
  f.globe.click(); f.document.fire('click', { target: new Element() }); assert.equal(f.dropdown.classList.contains('open'), false);
});

function analytics() {
  const document = new Element(); const html = new Element({ 'data-lang': 'zh', lang: 'zh-CN' }); document.documentElement = html;
  const window = new Element(); window.__APP_LANG__ = 'zh'; window.location = new URL('https://bookrank.test/analytics?lang=zh');
  const nodes = new Map(); const charts = [];
  for (const id of ['viewsChart', 'behaviorChart', 'dailyChart']) {
    const canvas = new Element(); canvas.id = id; canvas.getContext = () => canvas; const wrapper = new Element(); wrapper.appendChild(canvas);
    wrapper.querySelector = selector => selector === '.panel-status' ? wrapper.children.find(node => node.className === 'panel-status') || null : null;
    nodes.set(id, canvas);
  }
  document.getElementById = id => nodes.get(id) || null; document.createElement = () => new Element(); document.createTextNode = value => ({ textContent: value });
  class Chart { static defaults = {}; constructor(_canvas, config) { this.config = config; this.data = config.data; this.options = config.options; this.updates = 0; charts.push(this); } update() { this.updates++; } destroy() {} }
  const context = vm.createContext({ document, window, Chart, Date, Intl, URL, URLSearchParams, console, fetch: () => new Promise(() => {}) });
  const actual = scripts(source('templates/analytics_dashboard.html')).find(code => code.includes('function renderViewsChart'));
  assert.ok(actual, 'execute the real analytics script'); vm.runInContext(actual, context);
  return { context, charts, window, html, nodes };
}

test('weekly report chart preserves chronological UTC gaps and real zero counts on a linear date axis', () => {
  const f = analytics(); f.context.renderViewsChart([
    { date: '2026-10-08', view_count: 8 }, { date: '2026-10-04', view_count: 0 }, { date: '2026-09-27', view_count: 27 },
  ]);
  const chart = f.charts[0]; assert.equal(chart.options.scales.x?.type, 'linear'); assert.equal(chart.options.scales.y.beginAtZero, true);
  const points = JSON.parse(JSON.stringify(chart.data.datasets[0].data));
  assert.deepEqual(points.map(point => point.y), [27, 0, 8]);
  assert.equal(points[1].x - points[0].x, 7 * 86400000); assert.equal(points[2].x - points[1].x, 4 * 86400000);
  assert.equal(chart.options.scales.x.ticks.callback(points[0].x), '2026-09-27');
  assert.equal(chart.options.plugins.tooltip.callbacks.title([{ parsed: points[2] }]), '2026-10-08');
});

test('weekly report chart ignores missing/invalid dates without inventing today and exposes empty state', () => {
  const f = analytics(); f.context.renderViewsChart([{ date: null, view_count: 9 }, { date: 'unavailable', view_count: 2 }, { date: '2026-02-30', view_count: 1 }, { date: '2026-10-08suffix', view_count: 7 }]);
  assert.equal(f.charts[0].data.datasets[0].data.length, 0);
  const status = f.nodes.get('viewsChart').parentElement.querySelector('.panel-status');
  assert.equal(status?.dataset.statusKind, 'empty'); assert.equal(status?.textContent, '暂无数据');
});

test('behavior chart translates known event names and switches its labels while preserving factual counts', () => {
  const f = analytics(); f.context.renderBehaviorChart([
    { event_type: 'view_report', count: 5 }, { event_type: 'export_report', count: 2 }, { event_type: 'view_book', count: 1 },
  ]);
  const chart = f.charts[0]; assert.deepEqual(Array.from(chart.data.labels), ['阅读周报', '导出周报', '浏览图书']);
  const values = JSON.stringify(chart.data.datasets[0].data); const original = chart;
  f.window.__APP_LANG__ = 'en'; f.html.setAttribute('data-lang', 'en'); f.window.fire('languagechange', { detail: { language: 'en' } });
  assert.equal(f.charts[0], original); assert.deepEqual(Array.from(chart.data.labels), ['Read report', 'Export report', 'View book']);
  assert.equal(JSON.stringify(chart.data.datasets[0].data), values); assert.ok(chart.updates > 0);
});

for (const offscreen of [true, false]) test(`actual rankings selected publisher tab ${offscreen ? 'scrolls into' : 'stays in'} view without moving the page`, () => {
  const document = new Element(); document.documentElement = { lang: 'en' }; document.body = { lang: '' };
  const nav = new Element(); nav.clientWidth = 350; nav.scrollWidth = 640; nav.scrollLeft = 0;
  nav.getBoundingClientRect = () => ({ left: 0, right: 350 });
  const active = new Element({ 'aria-current': 'page', class: 'active' }); active.offsetLeft = offscreen ? 500 : 50; active.offsetWidth = 100;
  active.getBoundingClientRect = () => ({ left: active.offsetLeft - nav.scrollLeft, right: active.offsetLeft + active.offsetWidth - nav.scrollLeft });
  active.scrollIntoView = options => { assert.equal(options.block, 'nearest'); assert.equal(options.inline, 'nearest'); nav.scrollLeft = Math.max(0, active.offsetLeft + active.offsetWidth - nav.clientWidth); };
  nav.querySelector = () => active; nav.appendChild(active); document.querySelector = selector => selector.includes('rankings-tabs') ? nav : null;
  document.querySelectorAll = selector => selector.includes('rankings-tabs') ? [nav] : [];
  const window = new Element(); window.__APP_LANG__ = 'en'; window.scrollY = 280;
  const actual = scripts(source('templates/rankings.html')).find(code => code.includes('function applyLang'));
  assert.ok(actual); vm.runInNewContext(actual, { document, window });
  const rect = active.getBoundingClientRect(); assert.ok(rect.left >= 0 && rect.right <= nav.clientWidth, 'selected tab must be visible after initial render');
  assert.equal(window.scrollY, 280); if (!offscreen) assert.equal(nav.scrollLeft, 0);
});

function covers() {
  const window = { location: new URL('https://bookrank.test/awards'), setTimeout() {} };
  vm.runInNewContext(source('static/js/cover.js'), { window, URL, Date });
  return window.BookRankCover;
}

test('actual cover proxy recognition accepts only same-origin numeric award cover routes and the existing proxy', () => {
  const api = covers();
  for (const url of ['/cover?src=book', '/award-book/42/cover', '/award-book/42/cover?_r=1&_t=2', 'https://bookrank.test/award-book/42/cover']) assert.equal(api.isProxySrc(url), true, url);
  for (const url of ['https://foreign.test/award-book/42/cover', '//foreign.test/award-book/42/cover', '//foreign.test/cover?src=book', '/award-book/abc/cover', '/award-book/-1/cover', '/award-book/42/cover/extra', '/award-book/42', '/new-book/42/cover']) assert.equal(api.isProxySrc(url), false, url);
});

test('actual cold award cover placeholder retries exactly four times, deduplicates load and cleans retry metadata', () => {
  const api = covers(); const queued = []; const img = { dataset: {}, currentSrc: 'https://bookrank.test/static/default-cover.png', src: '/award-book/42/cover?_r=old&_t=old', getAttribute(name) { return name === 'src' ? '/award-book/42/cover?_r=old&_t=old' : ''; } };
  const options = { setTimeout: (fn, delay) => queued.push({ fn, delay }), now: () => 1234 };
  for (let attempt = 0; attempt < 4; attempt++) {
    assert.equal(api.scheduleRetry(img, options), true); assert.equal(api.scheduleRetry(img, options), false, 'one load must not duplicate pending retry');
    assert.equal(queued.length, attempt + 1); queued[attempt].fn();
    const url = new URL(img.src, 'https://bookrank.test'); assert.equal(url.pathname, '/award-book/42/cover'); assert.equal(url.searchParams.get('_r'), String(attempt)); assert.equal(url.searchParams.get('_t'), '1234');
  }
  assert.deepEqual(queued.map(job => job.delay), [800, 2000, 5000, 12000]); assert.equal(img.dataset.coverProxy, '/award-book/42/cover');
  assert.equal(api.scheduleRetry(img, options), false); assert.equal(queued.length, 4);
  img.currentSrc = 'https://bookrank.test/cache/images/real.jpg'; img.dataset.coverRetryCount = '0'; assert.equal(api.scheduleRetry(img, options), false);
  assert.equal(api.toSrc('https://images.test/book.jpg'), '/cover?src=https%3A%2F%2Fimages.test%2Fbook.jpg');
});

for (const locale of ['en', 'zh']) test(`actual ${locale} desktop new-books template puts four advanced controls in one native disclosure but keeps search/export/results reachable`, () => {
  const repo = process.cwd(); const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root: repo, name: 'new_books.html', url: '/new-books?lang=' + locale, locale, actual_display_labels: true,
      context: { books: [], publishers: [], publisher_kind: {}, publisher_labels: {}, categories: [], category_alias_labels: {}, stats: { total_books: 0, active_publishers: 0 }, selected_days: 30, selected_publication_status: 'all', selected_publisher: '', selected_category: '', search_query: '', future_preview_days: 14, total: 0, total_pages: 1, page: 1, per_page: 20 } }),
    encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  const rendered = JSON.parse(result.stdout); const find = id => rendered.nodes.find(node => node.attrs.id === id);
  const advanced = find('new-books-advanced-filters'); assert.equal(advanced?.tag, 'details', 'native keyboard-operable advanced disclosure required');
  assert.equal(Object.hasOwn(advanced.attrs, 'open'), true, 'without JS every filter remains available');
  const advancedIndex = rendered.nodes.indexOf(advanced); const form = find('filter-form'); const formIndex = rendered.nodes.indexOf(form);
  for (const id of ['publisher-filter', 'category-filter', 'days-filter', 'publication-status-filter']) {
    const control = find(id); assert.ok(control.ancestors.includes(advancedIndex), id); assert.ok(control.ancestors.includes(formIndex), 'form association retained');
  }
  for (const id of ['search-input', 'btn-search', 'btn-clear', 'btn-export', 'active-filters', 'result-summary']) assert.equal(find(id).ancestors.includes(advancedIndex), false, id);
  const selected = id => rendered.nodes.find(node => node.tag === 'option' && node.ancestors.includes(rendered.nodes.indexOf(find(id))) && Object.hasOwn(node.attrs, 'selected'));
  assert.equal(selected('days-filter').attrs.value, '30'); assert.equal(selected('publication-status-filter').attrs.value, 'all');
  const scope = find('new-books-scope'); assert.equal(scope?.tag, 'details');
  const windowText = rendered.nodes.find(node => (node.attrs.class || '').split(/\s+/).includes('collection-window'));
  assert.ok(windowText.ancestors.includes(rendered.nodes.indexOf(scope)), 'full date-window explanation remains accessible');
});

test('actual responsive new-books initialization collapses only narrow screens and preserves user toggles until breakpoint changes', () => {
  const actual = scripts(source('templates/new_books.html')).find(code => code.includes('initNewBooksResponsiveFilters'));
  assert.ok(actual, 'real responsive initializer required');
  for (const narrow of [true, false]) {
    const advanced = new Element(); advanced.open = true; const scope = new Element(); scope.open = true; const media = new Element(); media.matches = narrow;
    const document = { getElementById: id => ({ 'new-books-advanced-filters': advanced, 'new-books-scope': scope })[id] || null };
    const window = { matchMedia: query => { assert.equal(query, '(max-width: 768px)'); return media; } };
    vm.runInNewContext(actual, { document, window });
    assert.equal(advanced.open, !narrow); assert.equal(scope.open, !narrow);
    advanced.open = narrow; assert.equal(advanced.open, narrow, 'user can expand or collapse the native disclosure');
    media.matches = !narrow; media.fire('change', { matches: media.matches }); assert.equal(advanced.open, narrow); assert.equal(scope.open, narrow);
  }
});

const flush = () => new Promise(resolve => setImmediate(resolve));
function redirectedCover(responder, src = '/award-book/42/cover', imageOptions = {}) {
  const calls = []; const timers = []; const document = new Element();
  const img = { tagName: 'IMG', dataset: {}, src, currentSrc: new URL(src, 'https://bookrank.test').href, complete: false, naturalWidth: 280, naturalHeight: 415,
    getAttribute(name) { return name === 'src' ? this.src : ''; } };
  Object.assign(img, imageOptions);
  document.querySelectorAll = () => [img];
  const window = { location: new URL('https://bookrank.test/'), AbortController,
    fetch(url, options) { calls.push({ url, options }); return responder(url, options); },
    setTimeout(callback, delay) { const task = { callback, delay, cancelled: false }; timers.push(task); return task; },
    clearTimeout(task) { if (task) task.cancelled = true; } };
  vm.runInNewContext(source('static/js/cover.js'), { window, URL, Date, AbortController, fetch: window.fetch, console });
  window.BookRankCover.bind(document);
  return { img, document, calls, timers, api: window.BookRankCover, load: () => document.fire('load', { target: img }) };
}
const headResponse = (url, status = 200, headers = {}) => ({ ok: status >= 200 && status < 300, status, url, headers: { get: name => Object.entries(headers).find(([key]) => key.toLowerCase() === name.toLowerCase())?.[1] || null } });

for (const src of ['/award-book/42/cover', '/cover?src=remote']) test(`actual ${src} image load with unchanged proxy currentSrc detects redirected placeholder and starts bounded retry`, async () => {
  let release; const f = redirectedCover(() => new Promise(resolve => { release = resolve; }), src);
  f.load(); f.load(); assert.equal(f.calls.length, 1, 'duplicate load must not duplicate in-flight HEAD');
  assert.equal(f.calls[0].options.method, 'HEAD');
  release(headResponse('https://bookrank.test/static/default-cover.png')); await flush();
  const retries = f.timers.filter(task => !task.cancelled && f.api.RETRY_DELAYS_MS.includes(task.delay));
  assert.equal(retries.length, 1, 'browser currentSrc remains proxy after redirect; confirmed placeholder must still retry');
  assert.equal(f.img.dataset.coverRetryCount, '1'); retries[0].callback();
  assert.equal(new URL(f.img.src, 'https://bookrank.test').pathname, new URL(src, 'https://bookrank.test').pathname);
});

test('actual proxy image whose initial GET was a placeholder adopts the safe already-warmed cache header once', async () => {
  const cached = '/cache/images/' + 'a'.repeat(32) + '.jpg';
  const f = redirectedCover(async () => headResponse('https://bookrank.test/award-book/42/cover', 200, { 'X-Cover-Source': 'cache', 'X-Cover-Path': cached }));
  f.load(); await flush(); assert.equal(f.img.src, cached, 'HEAD can become warm after the original image GET returned the placeholder');
  f.img.currentSrc = new URL(cached, 'https://bookrank.test').href; f.load(); await flush();
  assert.equal(f.calls.length, 1, 'the real cached image must not start another HEAD or proxy reload');
  assert.equal(f.timers.filter(task => !task.cancelled).length, 0);
});

test('actual cover HEAD rejects external requests, foreign final URLs and malformed public cache paths', async () => {
  for (const src of ['//foreign.test/award-book/42/cover', '//foreign.test/cover?src=remote', '/award-book/nope/cover']) {
    const f = redirectedCover(async () => { throw new Error('external source must never be requested'); }, src); f.load(); await flush(); assert.equal(f.calls.length, 0);
  }
  for (const cachePath of ['//foreign.test/cache/images/' + 'a'.repeat(32) + '.jpg', 'https://foreign.test/cache/images/' + 'a'.repeat(32) + '.jpg', '/cache/images/not-a-hash.jpg', '/cache/images/' + 'a'.repeat(32) + '.jpg?other=1']) {
    const f = redirectedCover(async () => headResponse('https://bookrank.test/award-book/42/cover', 200, { 'X-Cover-Source': 'cache', 'X-Cover-Path': cachePath })); f.load(); await flush();
    assert.equal(f.img.src, '/award-book/42/cover'); assert.equal(f.timers.filter(task => !task.cancelled).length, 0);
  }
  const foreign = redirectedCover(async () => headResponse('https://foreign.test/static/default-cover.png')); foreign.load(); await flush(); assert.equal(foreign.img.src, '/award-book/42/cover'); assert.equal(foreign.timers.filter(task => !task.cancelled).length, 0);
});

test('actual cover HEAD failure and 404 do not fabricate pending state and release deduplication for later load', async () => {
  for (const reject of [false, true]) {
    const f = redirectedCover(async () => { if (reject) throw new Error('network unavailable'); return headResponse('https://bookrank.test/award-book/42/cover', 404); });
    f.load(); await flush(); f.load(); await flush(); assert.equal(f.calls.length, 2);
    assert.equal(f.img.src, '/award-book/42/cover'); assert.equal(f.timers.filter(task => !task.cancelled).length, 0);
    assert.equal(f.img.dataset.coverRetryCount, undefined);
  }
});

test('actual cover HEAD timeout aborts and releases the probe instead of keeping the image permanently pending', async () => {
  const f = redirectedCover((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')));
  }));
  f.load(); assert.equal(f.calls.length, 1); const timeout = f.timers.find(task => !task.cancelled);
  assert.ok(timeout && timeout.delay <= 10000, 'bounded HEAD timeout required'); timeout.callback(); await flush();
  assert.equal(f.calls[0].options.signal.aborted, true); f.load(); assert.equal(f.calls.length, 2, 'timed-out probe marker must clear');
  const retry = f.timers.find(task => !task.cancelled); retry.callback(); await flush();
  assert.equal(f.img.dataset.coverRetryCount, undefined); assert.equal(f.img.src, '/award-book/42/cover');
});

test('an old aborted HEAD finalizer cannot clear the deduplication marker of a newer image probe', async () => {
  const f = redirectedCover((_url, options) => new Promise((_resolve, reject) => {
    options.signal.addEventListener('abort', () => reject(new Error('aborted')));
  }));
  f.load(); f.timers.find(task => !task.cancelled).callback();
  f.load(); assert.equal(f.calls.length, 2, 'timeout cleanup allows a new probe immediately');
  await flush(); f.load(); assert.equal(f.calls.length, 2, 'the newer pending probe must still suppress duplicate loads after the old finalizer');
  f.timers.filter(task => !task.cancelled).at(-1).callback(); await flush();
});

for (const name of ['award_book_detail.html', 'mobile/award_book_detail.html']) test(`${name} renders a readable neutral cover and an accessible no-JavaScript cover link`, () => {
  const repo = process.cwd(); const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root: repo, name, url: '/award-book/42?lang=en', locale: 'en', actual_display_labels: true,
      context: { book: { id: 42, title: 'Cover contract book', title_zh: '', author: 'Author', isbn13: '9780306406157', isbn10: '', description: '', description_zh: '', details: '', publisher: '', cover_local_path: '', price: null, publication_date: null, page_count: null, award: null, buy_links: [] }, shown_title: 'Cover contract book', safe_title_en: 'Cover contract book', safe_title_zh: 'Cover contract book', other_title: '', shown_desc: '', shown_author: 'Author', shown_author_en: 'Author', shown_author_zh: 'Author', related_books: [], back_url: '/awards?lang=en' } }),
    encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  const rendered = JSON.parse(result.stdout); const img = rendered.nodes.find(node => node.tag === 'img' && node.attrs['data-neutral-cover-feedback'] === '1');
  assert.ok(img, 'actual award cover must opt into neutral feedback'); assert.equal(Object.hasOwn(img.attrs, 'hidden'), true);
  const placeholder = rendered.nodes.find(node => (node.attrs.class || '').includes('neutral-cover-placeholder'));
  assert.ok(placeholder?.text.includes('No cover')); assert.equal(Object.hasOwn(placeholder.attrs, 'hidden'), false);
  const link = rendered.nodes.find(node => node.tag === 'a' && node.attrs.href === '/award-book/42/cover' && node.ancestors.some(index => rendered.nodes[index].tag === 'noscript'));
  assert.ok(link?.text.includes('View'), 'without JavaScript the real cover remains accessible');
  if (name === 'award_book_detail.html') assert.equal(link.ancestors.some(index => (rendered.nodes[index].attrs.class || '').split(/\s+/).includes('detail-cover')), false, 'no-JavaScript link must remain outside the full-height overflow-hidden cover box');
});

test('actual marked award cover retains neutral feedback during pending HEAD and reveals a genuine cache image only after load', async () => {
  const cached = '/cache/images/' + 'b'.repeat(32) + '.jpg';
  const f = redirectedCover(async () => headResponse('https://bookrank.test/award-book/42/cover', 200, { 'X-Cover-Source': 'cache', 'X-Cover-Path': cached }));
  const placeholder = new Element(); placeholder.classList.add('m-neutral-cover-placeholder'); placeholder.hidden = false;
  f.img.dataset.neutralCoverFeedback = '1'; f.img.nextElementSibling = placeholder; f.img.hidden = true;
  f.load(); await flush(); assert.equal(f.img.src, cached); assert.equal(f.img.hidden, true); assert.equal(placeholder.hidden, false);
  f.img.currentSrc = new URL(cached, 'https://bookrank.test').href; f.load(); await flush();
  assert.equal(f.img.hidden, false); assert.equal(placeholder.hidden, true); assert.equal(f.calls.length, 1);
  f.document.fire('error', { target: f.img }); assert.equal(f.img.hidden, true); assert.equal(placeholder.hidden, false, 'later image failure must restore readable neutral feedback');
});

for (const rendered of ['en', 'zh']) test(`actual rankings ${rendered} SSR reloads only for a supported changed language and preserves every URL condition`, () => {
  const document = new Element(); document.documentElement = { lang: rendered }; document.body = { lang: '' };
  const nav = new Element({ 'data-rendered-lang': rendered }); const nodes = [new Element({ 'data-label-zh': '厂牌', 'data-label-en': 'Publisher' })];
  document.querySelector = selector => selector.startsWith('.rankings-tabs') ? nav : null;
  document.querySelectorAll = selector => selector === '[data-label-zh][data-label-en]' ? nodes : [];
  const replaced = []; const window = new Element(); window.__APP_LANG__ = rendered;
  window.location = { href: 'https://bookrank.test/rankings?tab=publishers&lang=' + rendered + '&view=list&page=3#result', replace: value => replaced.push(String(value)) };
  const actual = scripts(source('templates/rankings.html')).find(code => code.includes('function applyLang'));
  vm.runInNewContext(actual, { document, window, URL }); assert.deepEqual(replaced, [], 'initial apply must never reload');
  for (const language of [rendered, '', 'fr', 'zh-foreign', null]) window.fire('languagechange', { detail: { language } });
  window.fire('languagechange'); assert.deepEqual(replaced, [], 'same SSR, absent or unsupported event must never reload');
  const changed = rendered === 'en' ? 'zh' : 'en'; window.__APP_LANG__ = changed; document.documentElement.lang = changed;
  window.fire('languagechange', { detail: { language: changed } }); assert.equal(replaced.length, 1, 'full SSR content needs a genuine navigation');
  const destination = new URL(replaced[0], window.location.href);
  assert.equal(destination.origin, 'https://bookrank.test'); assert.equal(destination.pathname, '/rankings'); assert.equal(destination.hash, '#result');
  assert.deepEqual([...destination.searchParams], [['tab', 'publishers'], ['lang', changed], ['view', 'list'], ['page', '3']]);
  assert.equal(nodes[0].getAttribute('data-label'), changed === 'zh' ? '厂牌' : 'Publisher');
});

for (const complete of [false, true]) test(`actual marked direct cache cover ${complete ? 'already loaded' : 'loading now'} reveals without any HEAD`, async () => {
  const placeholder = new Element(); placeholder.classList.add('neutral-cover-placeholder'); placeholder.hidden = false;
  const f = redirectedCover(() => { throw new Error('real cached image needs no HEAD'); }, '/cache/images/' + 'c'.repeat(32) + '.jpg', {
    complete, hidden: true, dataset: { neutralCoverFeedback: '1' }, nextElementSibling: placeholder,
  });
  if (!complete) f.load(); await flush(); assert.equal(f.calls.length, 0); assert.equal(f.img.hidden, false); assert.equal(placeholder.hidden, true);
});

test('actual marked missing cover and failed image keep readable feedback while ordinary direct images remain unaffected', async () => {
  const placeholder = new Element(); placeholder.classList.add('neutral-cover-placeholder'); placeholder.hidden = false;
  const f = redirectedCover(async () => headResponse('https://bookrank.test/award-book/42/cover', 404), undefined, {
    hidden: true, dataset: { neutralCoverFeedback: '1' }, nextElementSibling: placeholder,
  });
  f.load(); await flush(); assert.equal(f.img.hidden, true); assert.equal(placeholder.hidden, false); assert.equal(f.img.dataset.coverRetryCount, undefined);
  const failed = redirectedCover(() => { throw new Error('broken direct cover must not probe'); }, '/cache/images/' + 'd'.repeat(32) + '.jpg', {
    complete: true, naturalWidth: 0, hidden: true, dataset: { neutralCoverFeedback: '1' }, nextElementSibling: placeholder,
  });
  assert.equal(failed.img.hidden, true); assert.equal(placeholder.hidden, false); assert.equal(failed.calls.length, 0);
  const ordinary = redirectedCover(() => { throw new Error('ordinary direct cover must not probe'); }, 'https://external.test/actual-cover.jpg');
  ordinary.load(); await flush(); assert.equal(ordinary.img.hidden, undefined); assert.equal(ordinary.calls.length, 0);
});

for (const sourcePath of ['/award-book/42/cover', '/cover?src=remote']) test(`actual ${sourcePath} final fourth image retry gets one warm HEAD and reveals after genuine cache load`, async () => {
  const cached = '/cache/images/' + 'e'.repeat(32) + '.jpg'; let probes = 0;
  const placeholder = new Element(); placeholder.classList.add('neutral-cover-placeholder'); placeholder.hidden = false;
  const f = redirectedCover(async () => ++probes <= 4
    ? headResponse('https://bookrank.test/static/default-cover.png')
    : headResponse(new URL(sourcePath, 'https://bookrank.test').href, 200, { 'X-Cover-Source': 'cache', 'X-Cover-Path': cached }), sourcePath,
  { hidden: true, dataset: { neutralCoverFeedback: '1' }, nextElementSibling: placeholder });
  for (const delay of f.api.RETRY_DELAYS_MS) {
    f.load(); await flush(); const job = f.timers.find(task => !task.cancelled && task.delay === delay);
    assert.ok(job, `actual image retry scheduled at ${delay}ms`); job.cancelled = true; job.callback();
    f.img.currentSrc = new URL(f.img.src, 'https://bookrank.test').href;
  }
  assert.equal(f.img.dataset.coverRetryCount, '4'); f.img.naturalWidth = 120; f.img.naturalHeight = 180;
  f.load(); await flush(); assert.equal(f.calls.length, 5, 'one HEAD after initial GET plus each of four retry GETs');
  assert.equal(f.img.src, cached, 'last GET can be real while currentSrc still names the proxy'); assert.equal(f.img.hidden, true);
  assert.equal(f.timers.filter(task => !task.cancelled).length, 0, 'no fifth image retry allowed');
  f.img.currentSrc = new URL(cached, 'https://bookrank.test').href; f.load(); await flush();
  assert.equal(f.img.hidden, false); assert.equal(placeholder.hidden, true); assert.equal(f.calls.length, 5);
});

test('actual exhausted final proxy probe is attempted once across placeholder, 404, failure and timeout', async () => {
  for (const outcome of ['placeholder', '404', 'error', 'timeout']) {
    const f = redirectedCover((_url, options) => {
      if (outcome === 'timeout') return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new Error('aborted'))));
      if (outcome === 'error') return Promise.reject(new Error('unavailable'));
      return Promise.resolve(headResponse(outcome === '404' ? 'https://bookrank.test/award-book/42/cover' : 'https://bookrank.test/static/default-cover.png', outcome === '404' ? 404 : 200));
    }, '/award-book/42/cover?_r=3&_t=123', { dataset: { coverRetryCount: '4' } });
    f.load(); f.load(); assert.equal(f.calls.length, 1, 'final probe must run, with in-flight deduplication');
    if (outcome === 'timeout') { f.timers.find(task => !task.cancelled).callback(); }
    await flush(); f.load(); await flush(); assert.equal(f.calls.length, 1, 'failed or completed final probe must not restart indefinitely');
    assert.equal(f.img.dataset.coverRetryCount, '4'); assert.equal(f.timers.filter(task => !task.cancelled).length, 0);
  }
});
