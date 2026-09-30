import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { spawnSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const repo = process.env.ROUND2_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
function source(name) { return fs.readFileSync(path.join(repo, name), 'utf8').replace(/^\uFEFF/, ''); }
class Element {
  constructor(value = '') { this.value = value; this.textContent = ''; this.hidden = false; this.style = {}; this.dataset = {}; this.listeners = new Map(); this.queries = new Map(); this.options = []; }
  addEventListener(type, fn) { const list = this.listeners.get(type) || []; list.push(fn); this.listeners.set(type, list); }
  fire(type, extra = {}) { const event = { target: this, key: '', preventDefault() {}, ...extra }; for (const fn of this.listeners.get(type) || []) fn.call(this, event); }
  querySelectorAll(selector) { return this.queries.get(selector) || []; }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
  getAttribute(name) { if (name.startsWith('data-')) return this.dataset[name.slice(5).replace(/-([a-z])/g, (_, c) => c.toUpperCase())] ?? null; return this[name] ?? null; }
  focus() { this.focused = true; }
}
function harness(url = 'https://bookrank.test/awards?view=list&lang=en&page=4&per_page=24') {
  const document = new Element(); const ids = new Map(); const selectors = new Map();
  document.getElementById = id => ids.get(id) || null;
  document.querySelectorAll = selector => selectors.get(selector) || [];
  document.querySelector = selector => document.querySelectorAll(selector)[0] || null;
  document.documentElement = { dataset: { lang: 'en' }, lang: 'en', getAttribute: key => key === 'lang' ? 'en' : 'en' };
  const window = new Element(); let location = new URL(url);
  window.__APP_LANG__ = 'en';
  window.location = { get href() { return location.href; }, set href(value) { location = new URL(value, location); }, get search() { return location.search; }, get pathname() { return location.pathname; }, get origin() { return location.origin; } };
  const history = { replaceState(_a, _b, value) { window.location.href = value; }, pushState(_a, _b, value) { window.location.href = value; } };
  const context = vm.createContext({ document, window, location: window.location, history, URL, URLSearchParams, console, showLoading() {}, setTimeout() {}, navigator: {}, sessionStorage: { getItem() { return null; }, setItem() {} } });
  return { document, window, ids, selectors, context, url: () => new URL(window.location.href) };
}
function scripts(html) { return [...html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/gi)].map(match => match[1]); }
function run(script, h) { assert.ok(script, 'actual source script must exist'); vm.runInContext(script.replace(/\{\{\s*get_locale\(\)\s*\}\}/g, 'en').replace(/\{\{\s*_locale\s*\}\}/g, 'en'), h.context); h.document.fire('DOMContentLoaded'); }
function awardsHarness(grid) {
  const h = harness();
  if (grid) h.ids.set('books-grid', grid);
  for (const [id, value] of Object.entries({ 'award-select': 'Booker', 'year-select': '2026', 'category-select': 'winner', 'search-input': 'Rain', 'btn-apply': '', 'btn-clear': '' })) h.ids.set(id, new Element(value));
  const script = scripts(source('templates/awards.html')).find(s => s.includes('function applyFilters'));
  assert.ok(script, 'real awards script missing');
  const start = script.indexOf("document.addEventListener('DOMContentLoaded', () =>");
  assert.notEqual(start, -1, 'real awards event initialization missing');
  run(script.slice(start), h);
  return h;
}
test('awards change controls remain draft until actual Apply click', () => {
  const h = awardsHarness(); const before = h.url().href;
  h.ids.get('award-select').value = 'Pulitzer'; h.ids.get('award-select').fire('change');
  h.ids.get('year-select').fire('change'); h.ids.get('category-select').fire('change');
  assert.equal(h.url().href, before);
  h.ids.get('btn-apply').fire('click');
  assert.equal(h.url().searchParams.get('award'), 'Pulitzer');
});
test('awards Apply preserves view/lang and all conditions while resetting page', () => {
  const h = awardsHarness(); h.ids.get('btn-apply').fire('click'); const p = h.url().searchParams;
  assert.equal(p.get('view'), 'list'); assert.equal(p.get('lang'), 'en');
  assert.equal(p.get('year'), '2026'); assert.equal(p.get('category'), 'winner'); assert.equal(p.get('search'), 'Rain');
  assert.equal(p.get('page') || '1', '1');
});
test('awards Clear removes filters but preserves view/lang', () => {
  const h = awardsHarness(); h.ids.get('btn-clear').fire('click'); const p = h.url().searchParams;
  assert.equal(p.get('view'), 'list'); assert.equal(p.get('lang'), 'en');
  for (const key of ['award', 'year', 'category', 'search']) assert.equal(p.has(key), false);
  assert.equal(p.get('page') || '1', '1');
});

test('awards actual delegated handler navigates only canonical positive safe integer IDs', () => {
  for (const id of ['1', '42', '9007199254740991']) {
    const grid = new Element(); const h = awardsHarness(grid); const origin = h.url();
    const card = { getAttribute: name => name === 'data-award-book-id' ? id : null };
    const target = { closest: selector => selector === '.card[data-award-book-id]' ? card : null };
    grid.fire('click', { target });
    assert.equal(h.url().pathname, '/award-book/' + Number(id)); assert.equal(h.url().searchParams.get('lang'), 'en');
    assert.equal(h.url().searchParams.get('return_to'), origin.pathname + origin.search);
  }
});

test('awards actual delegated handler rejects malformed, unsafe and markup/path IDs', () => {
  for (const id of ['1\n', '1\r', '1\u2028', '1\u2029', '<img src=x onerror=alert(1)>', '../../evil', null, '', ' ', '0', '-1', 'NaN', 'Infinity', '1.5', '1e2', '10evil', '+10', '0x10', '9007199254740992']) {
    const grid = new Element(); const h = awardsHarness(grid); const before = h.url().href;
    const card = { getAttribute: name => name === 'data-award-book-id' ? id : null };
    const target = { closest: selector => selector === '.card[data-award-book-id]' ? card : null };
    grid.fire('click', { target }); assert.equal(h.url().href, before, 'invalid ID must never navigate: ' + String(id));
  }
});

test('awards real handler leaves native modifier links intact and delegates ISBN favorite once', () => {
  const grid = new Element(); const h = awardsHarness(grid); const before = h.url().href;
  const anchor = {}; grid.fire('click', { ctrlKey: true, target: { closest: selector => selector === 'a[href]' ? anchor : null } });
  assert.equal(h.url().href, before);
  const calls = []; h.context.toggleFavorite = (button, isbn) => calls.push({ button, isbn });
  const button = new Element(); button.dataset.isbn = '9780385550369'; button.disabled = false; let stops = 0;
  const event = { target: { closest: selector => selector === '.btn-favorite' ? button : null }, stopPropagation() { stops++; } };
  grid.fire('click', event); assert.equal(calls.length, 1); assert.equal(calls[0].button, button); assert.equal(calls[0].isbn, '9780385550369');
  button.disabled = true; grid.fire('click', event); assert.equal(calls.length, 1); assert.equal(stops, 2); assert.equal(h.url().href, before);
});

test('source script extractor handles upper/mixed case and never scripture tags', () => {
  const html = '<SCRIPT nonce="test">upper()</SCRIPT><script>lower()</script><ScRiPt>mixed()</sCrIpT><scripture>never()</scripture>';
  assert.deepEqual(scripts(html), ['upper()', 'lower()', 'mixed()']);
});

test('mock rejects nonempty HTML sink rather than offering pretend sanitization; empty clears nodes', () => {
  const node = new DomNode('DIV'); const child = new DomNode('SPAN'); child.textContent = 'kept'; node.appendChild(child);
  for (const value of ['<SCRIPT>alert(1)</SCRIPT>', '<scrip<script>is removed</script>t>alert(1)</script>', 'prefix<script', '<b>ordinary markup</b>']) {
    assert.throws(() => { node.innerHTML = value; }, /DomNode\.innerHTML setter does not support nonempty HTML/); assert.equal(node.textContent, 'kept');
  }
  node.innerHTML = ''; assert.equal(node.textContent, ''); assert.equal(node.children.length, 0);
});
function publisherHarness(mobile) {
  const h = harness('https://bookrank.test/publishers?lang=en');
  const input = new Element(); const count = new Element(); count.textContent = '2 sites';
  const clear = new Element(); const empty = new Element(); empty.hidden = true;
  const rows = [new Element(), new Element()]; rows[0].dataset = { name: '企鹅', nameEn: 'penguin' }; rows[1].dataset = { name: '哈珀', nameEn: 'harper' };
  const group = new Element(); group.queries.set(mobile ? '.m-publisher-card' : 'tbody tr', rows);
  h.ids.set(mobile ? 'm-publisher-search' : 'search-input', input);
  h.ids.set(mobile ? 'm-result-count' : 'result-count', count);
  h.ids.set(mobile ? 'm-clear-search-btn' : 'clear-search-btn', clear);
  h.ids.set(mobile ? 'm-no-results' : 'no-results', empty);
  h.selectors.set(mobile ? '.m-publisher-category' : '.publisher-group', [group]);
  const name = mobile ? 'templates/mobile/publishers.html' : 'templates/publishers.html';
  run(scripts(source(name)).find(s => s.includes(mobile ? 'm-publisher-search' : "'search-input'")), h);
  return { h, input, count, clear, empty, rows, group };
}
for (const mobile of [false, true]) test(`publisher ${mobile ? 'mobile' : 'desktop'} real input updates count/empty and Clear restores collection`, () => {
  const f = publisherHarness(mobile); f.input.value = '企鹅'; f.input.fire('input'); assert.match(f.count.textContent, /^1\b/);
  f.input.value = 'absent'; f.input.fire('input'); assert.match(f.count.textContent, /^0\b/); assert.equal(f.empty.hidden, false);
  f.clear.fire('click'); assert.equal(f.input.value, ''); assert.match(f.count.textContent, /^2\b/); assert.equal(f.empty.hidden, true);
  for (const row of f.rows) { assert.equal(row.hidden, false); assert.notEqual(row.style.display, 'none'); }
  assert.equal(f.input.focused, true);
});
function weeklyHarness(mobile) {
  const h = harness('https://bookrank.test/reports/weekly?month=2026-09&search=rain&lang=en');
  const month = new Element(); month.options = ['', '2026-09', '2026-08'].map(value => ({ value }));
  const input = new Element(); const clear = new Element(); const count = new Element(); count.textContent = 'not initialized'; const html = source(mobile ? 'templates/mobile/weekly_reports.html' : 'templates/weekly_reports.html');
  const markup = parseMarkup(html.split('{% block extra_js %}')[0]);
  const empty = markup.querySelector(mobile ? '#m-wr-no-results' : '.wr-no-results');
  const cards = [['2026-09', 'Rain', 'Observed summary'], ['2026-08', 'Rain', 'Other month'], ['2026-09', 'Snow', 'Different title']].map(([m, title, summary]) => {
    const c = new Element(); c.dataset = { month: m, date: m + '-20', title, summary };
    const titleEl = new Element(); titleEl.textContent = title; const summaryEl = new Element(); summaryEl.textContent = summary;
    c.queries.set(mobile ? '.m-report-title' : '.news-title', [titleEl]); c.queries.set(mobile ? '.m-report-summary' : '.news-summary', [summaryEl]); return c;
  });
  h.ids.set(mobile ? 'm-month-filter' : 'month-filter', month); h.ids.set('date-filter', month);
  h.ids.set(mobile ? 'm-search-input' : 'search-input', input);
  h.ids.set(mobile ? 'm-wr-filter-clear' : 'wr-filter-clear', clear); h.ids.set(mobile ? 'm-wr-filter-count' : 'wr-filter-count', count);
  if (empty) { h.ids.set('m-wr-no-results', empty); h.selectors.set('.wr-no-results', [empty]); }
  const emptyClear = markup.querySelector('#wr-empty-clear'); if (emptyClear) h.ids.set('wr-empty-clear', emptyClear);
  clear.click = () => clear.fire('click');
  h.selectors.set(mobile ? '.m-report-card' : '.report-card', cards);
  if (mobile) {
    const group = new Element(); group.querySelector = selector => selector.startsWith('.m-report-card') ? cards.find(c => c.style.display !== 'none') || null : null;
    group.queries.set('.m-report-card', cards); h.selectors.set('.m-report-group', [group]);
  }
  const script = scripts(source(mobile ? 'templates/mobile/weekly_reports.html' : 'templates/weekly_reports.html')).find(s => s.includes(mobile ? 'm-month-filter' : '.report-card'));
  run(script?.replace(/\{\{\s*_\((['"])(.*?)\1\)\s*\}\}/g, (_m, _q, text) => text), h);
  return { h, month, input, clear, count, empty, cards };
}
for (const mobile of [false, true]) {
  test(`weekly ${mobile ? 'mobile' : 'desktop'} restores URL month/search intersection and honest local count`, () => {
    const f = weeklyHarness(mobile); assert.equal(f.month.value, '2026-09'); assert.equal(f.input.value, 'rain');
    assert.notEqual(f.cards[0].style.display, 'none'); assert.equal(f.cards[1].style.display, 'none'); assert.equal(f.cards[2].style.display, 'none');
    assert.equal(f.count.textContent, '1 Matches in this list');
    f.input.value = 'absent'; f.input.fire('input'); assert.equal(f.count.textContent, '0 Matches in this list'); assert.equal(f.empty.style.display, 'block');
  });
  test(`weekly ${mobile ? 'mobile' : 'desktop'} Clear and popstate restore same collection preserving lang`, () => {
    const f = weeklyHarness(mobile); f.clear.fire('click'); assert.equal(f.month.value, ''); assert.equal(f.input.value, '');
    assert.equal(f.h.url().searchParams.get('lang'), 'en'); assert.equal(f.h.url().searchParams.has('month'), false); assert.equal(f.h.url().searchParams.has('search'), false);
    assert.equal(f.count.textContent, '3 Matches in this list'); for (const c of f.cards) assert.notEqual(c.style.display, 'none');
    f.h.window.location.href = '/reports/weekly?month=2026-08&search=rain&lang=en'; f.h.window.fire('popstate');
    assert.equal(f.count.textContent, '1 Matches in this list'); assert.equal(f.cards[0].style.display, 'none'); assert.notEqual(f.cards[1].style.display, 'none');
  });
}
const voidTags = new Set(['INPUT', 'IMG', 'BR', 'HR', 'META', 'LINK', 'USE']);
class DomNode extends Element {
  constructor(tag = 'DIV') { super(); this.tagName = tag.toUpperCase(); this.children = []; this.attributes = new Map(); this._text = ''; this.className = ''; this.disabled = false; this.classList = { add: name => { this.className += ' ' + name; }, remove: name => { this.className = this.className.split(/\s+/).filter(x => x !== name).join(' '); }, contains: name => this.className.split(/\s+/).includes(name) }; }
  set textContent(value) { this._text = String(value); if (this.children) this.children = []; }
  get textContent() { return this._text + (this.children || []).map(n => n.textContent).join(''); }
  set innerHTML(value) {
    if (String(value).length > 0) {
      throw new Error('DomNode.innerHTML setter does not support nonempty HTML. Use DOM node APIs (createElement, replaceChildren, textContent) instead.');
    }
    this.replaceChildren();
  }
  get innerHTML() { return this.textContent; }
  appendChild(node) { node.parentElement = this; node.parentNode = this; this.children.push(node); return node; }
  append(...nodes) { for (const node of nodes) this.appendChild(node); }
  removeChild(node) { this.children.splice(this.children.indexOf(node), 1); node.parentElement = null; }
  remove() { this.parentElement?.removeChild(this); }
  replaceChildren(...nodes) { this.children = []; this._text = ''; this.append(...nodes); }
  get firstChild() { return this.children[0] || null; }
  setAttribute(key, value) { this.attributes.set(key, String(value)); if (key === 'id') this.id = value; if (key === 'class') this.className = value; if (key === 'disabled') this.disabled = true; }
  getAttribute(key) { return this.attributes.get(key) ?? super.getAttribute(key); }
  removeAttribute(key) { this.attributes.delete(key); }
  matches(selector) { return selector.startsWith('#') ? this.id === selector.slice(1) : selector.startsWith('.') ? this.className.split(/\s+/).includes(selector.slice(1)) : this.tagName === selector.toUpperCase(); }
  querySelectorAll(selector) { return this.children.flatMap(n => [...(n.matches(selector) ? [n] : []), ...n.querySelectorAll(selector)]); }
  closest(selector) { for (let n = this; n; n = n.parentElement) if (n.matches(selector)) return n; return null; }
  click() { if (!this.disabled) this.fire('click'); }
}
function parseMarkup(html) {
  const root = new DomNode('ROOT'); const stack = [root]; let previous = 0;
  for (const match of html.matchAll(/<\/?[a-z][^>]*>/gi)) {
    const tag = match[0]; const parent = stack.at(-1); parent._text += html.slice(previous, match.index).replace(/\{[%{][\s\S]*?[}%]\}/g, ''); previous = match.index + tag.length;
    const name = tag.match(/^<\/?([a-z][\w-]*)/i)[1].toUpperCase();
    if (tag.startsWith('</')) { const index = stack.findLastIndex(n => n.tagName === name); if (index > 0) stack.length = index; continue; }
    const node = new DomNode(name);
    for (const a of tag.matchAll(/([\w-]+)(?:="([^"]*)"|='([^']*)')?/g)) { if (a.index <= 1) continue; node.setAttribute(a[1], a[2] ?? a[3] ?? ''); }
    parent.appendChild(node); if (!voidTags.has(name) && !tag.endsWith('/>')) stack.push(node);
  }
  return root;
}
function cacheHarness(fetch) {
  const html = source('templates/cache_management.html'); const markup = parseMarkup(html.slice(0, html.indexOf('{% block extra_js %}')));
  const document = new Element(); document.documentElement = { lang: 'en' }; document.createElement = name => new DomNode(name);
  document.getElementById = id => markup.querySelector('#' + id); document.querySelectorAll = selector => markup.querySelectorAll(selector); document.querySelector = selector => document.querySelectorAll(selector)[0] || null;
  const context = vm.createContext({ document, fetch, console: { error() {} }, showToast() {}, confirm: () => true });
  const script = scripts(html).find(s => s.includes('async function loadTranslationStats'));
  assert.ok(script, 'actual cache script missing'); vm.runInContext(script, context);
  return { document, context, call: code => vm.runInContext(code, context) };
}
function reply(status, data) { return { status, ok: status >= 200 && status < 300, json: async () => data }; }
function deferred() { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; }

test('cache actual initial HTML disables all clear buttons before requests settle', () => {
  const f = cacheHarness(() => new Promise(() => {}));
  for (const id of ['btn-clear-translation', 'btn-clear-all-translation', 'btn-clear-api', 'btn-clear-expired']) { const button = f.document.getElementById(id); assert.ok(button); assert.equal(button.disabled, true); }
});
for (const status of [401, 403]) test(`cache HTTP ${status} renders authorization state, never empty, and keeps clears disabled`, async () => {
  const f = cacheHarness(async () => reply(status, { success: false, message: 'unauthorized' }));
  await f.call('loadTranslationStats()'); await f.call('loadTranslationRecords()');
  const text = f.document.getElementById('translation-list').textContent;
  assert.match(text, /Insufficient permissions/); assert.doesNotMatch(text, /No .*records|暂无.*记录/);
  assert.equal(f.document.getElementById('btn-clear-translation').disabled, true);
});
test('cache late successful stats cannot override a prior authorization denial', async () => {
  const stats = deferred(); const f = cacheHarness(url => url.endsWith('/stats') ? stats.promise : Promise.resolve(reply(403, { success: false })));
  const pending = f.call('loadTranslationStats()'); await f.call('loadTranslationRecords()');
  stats.resolve(reply(200, { success: true, data: { cache: { total_count: 9 } } })); await pending;
  assert.equal(f.document.getElementById('btn-clear-translation').disabled, true);
  assert.notEqual(String(f.document.getElementById('trans-total-count').textContent), '9');
});
test('cache 500 and successful empty are visibly distinct with a working retry', async () => {
  let failed = true; let requests = 0;
  const f = cacheHarness(async () => { requests++; return failed ? reply(500, { success: false }) : reply(200, { success: true, data: { records: [] } }); });
  await f.call('loadAPIRecords()'); const list = f.document.getElementById('api-list');
  assert.match(list.textContent, /Failed to load/); assert.doesNotMatch(list.textContent, /No API cache records/);
  const retry = list.querySelector('button'); assert.ok(retry, 'failure exposes actual retry'); failed = false; retry.click(); await new Promise(resolve => setImmediate(resolve));
  assert.equal(requests, 2); assert.match(list.textContent, /No API cache records/); assert.equal(list.querySelector('button'), null);
});
for (const [urlLang, saved] of [['zh', 'en'], ['en', 'zh']]) test(`explicit URL ${urlLang} wins over stored ${saved} in every base language phase`, () => {
  const h = harness('https://bookrank.test/awards?lang=' + urlLang + '&view=compact');
  const store = new Map([['app_language', saved], ['bookrank_language', saved]]); const applied = [];
  h.context.localStorage = { getItem: key => store.get(key), setItem: (key, val) => store.set(key, val) };
  h.context.navigator = { language: saved }; h.context.applyPageTranslation = lang => applied.push(lang);
  const baseScripts = scripts(source('templates/base.html'));
  const early = baseScripts.find(s => s.includes('var ssrLang'));
  const late = baseScripts.find(s => s.includes('var serverLang'));
  assert.ok(early && late, 'both real template phases must exist');
  const renderLocale = script => script.replace(/\{\{\s*get_locale\(\)\s*\}\}/g, urlLang);
  vm.runInContext(renderLocale(early), h.context);
  assert.equal(h.window.__APP_LANG__, urlLang); assert.equal(h.document.documentElement.lang, urlLang === 'zh' ? 'zh-CN' : 'en');
  const base = source('static/js/base.js'); const start = base.indexOf('    function getCurrentLang()'); const end = base.indexOf('\n    /**', start);
  assert.ok(start >= 0 && end > start, 'real getter source missing'); vm.runInContext(base.slice(start, end), h.context);
  assert.equal(vm.runInContext('getCurrentLang()', h.context), urlLang);
  vm.runInContext(renderLocale(late), h.context);
  assert.deepEqual(applied, [urlLang]); assert.equal(store.get('app_language'), urlLang); assert.equal(store.get('bookrank_language'), urlLang);
});
test('manual language setter updates URL and shared language while preserving all return/filter state', () => {
  const returnTo = '/new-books?publication_status=upcoming&search=rain&page=2';
  const h = harness('https://bookrank.test/awards?lang=zh&view=compact&award=Booker&page=3&return_to=' + encodeURIComponent(returnTo) + '#results');
  const store = new Map([['app_language', 'zh'], ['bookrank_language', 'zh']]);
  h.context.localStorage = { getItem: key => store.get(key), setItem: (key, value) => store.set(key, value) };
  h.context.navigator = { language: 'zh' }; h.context.applyPageTranslation = () => {}; h.context.t = key => key;
  h.context.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
  h.window.dispatchEvent = ev => h.window.fire(ev.type, ev); h.window.__APP_LANG__ = 'zh';
  const translations = source('static/js/translations.js'); const start = translations.indexOf('function setGlobalLanguage'); const end = translations.indexOf('// 暴露到全局', start);
  assert.ok(start >= 0 && end > start, 'real setter must exist'); vm.runInContext(translations.slice(start, end), h.context);
  vm.runInContext("setGlobalLanguage('en')", h.context);
  const url = h.url(); assert.equal(url.searchParams.get('lang'), 'en'); assert.equal(url.searchParams.get('award'), 'Booker'); assert.equal(url.searchParams.get('page'), '3');
  assert.equal(url.searchParams.get('view'), 'compact'); assert.equal(url.searchParams.get('return_to'), returnTo); assert.equal(url.hash, '#results'); assert.equal(h.window.__APP_LANG__, 'en');
  const base = source('static/js/base.js'); const bs = base.indexOf('    function getCurrentLang()'); const be = base.indexOf('\n    /**', bs);
  assert.ok(bs >= 0 && be > bs); vm.runInContext(base.slice(bs, be), h.context); assert.equal(vm.runInContext('getCurrentLang()', h.context), 'en');
});
test('analytics daily chart uses UTC linear dates and preserves actual zero/gaps across a month boundary', () => {
  const h = harness(); const canvas = new Element(); canvas.getContext = () => ({}); h.ids.set('dailyChart', canvas); const configs = [];
  h.context.Chart = function(_ctx, config) { configs.push(config); this.destroy = () => {}; };
  const html = source('templates/analytics_dashboard.html'); const actual = scripts(html).find(s => s.includes('function renderDailyChart'));
  const start = actual?.indexOf('        function renderDailyChart'); const end = actual?.indexOf('        function renderTopReports', start);
  assert.ok(start >= 0 && end > start, 'real daily renderer source must exist');
  vm.runInContext("let dailyChart = null; const chartColors = {greenBorder:'#000',greenLight:'#eee'};\n" + actual.slice(start, end), h.context);
  h.context.rows = [{ date: '2026-10-02', count: 1 }, { date: '2026-09-29', count: 3 }, { date: '2026-09-30', count: 0 }];
  vm.runInContext('renderDailyChart(rows)', h.context); const config = configs[0]; assert.ok(config);
  assert.equal(config.options.scales.x?.type, 'linear'); const points = config.data.datasets[0].data;
  assert.equal(points.length, 3); assert.equal(points[0].x, Date.parse('2026-09-29T00:00:00Z')); assert.equal(points[1].y, 0);
  assert.equal(points[2].x - points[0].x, 3 * 86400000); assert.equal(config.data.datasets[0].tension, 0);
  assert.equal(config.options.scales.x.ticks.callback(points[0].x), '2026-09-29');
  assert.equal(config.options.plugins.tooltip.callbacks.title([{ parsed: points[2] }]), '2026-10-02');
});

function renderJinja(fragment, context) {
  const code = "import json,sys; from jinja2 import Environment; sys.stdout.reconfigure(encoding='utf-8'); sys.stdin.reconfigure(encoding='utf-8'); x=json.load(sys.stdin); e=Environment(); e.globals['_']=lambda s:s; e.filters['format_title']=lambda s:s; print(e.from_string(x['fragment']).render(**x['context']))";
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', code], { input: JSON.stringify({ fragment, context }), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024 });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr); assert.ok(result.stdout.trim());
  return result.stdout;
}

function mobileLocaleContext(url, stored, server) {
  const h = harness(url); const values = new Map([['app_language', stored], ['bookrank_language', stored]]);
  h.context.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  h.document.documentElement.getAttribute = () => server;
  const text = source('static/mobile/js/mobile.js');
  const a = text.indexOf('    function getSavedLanguage'); const b = text.indexOf('    function updateLangMenu', a);
  const c = text.indexOf('    function switchLanguage'); const d = text.indexOf('    function initLangSwitcher', c);
  const constants = text.match(/const LANG_STORAGE_KEY[^;]+;[\s\S]*?const APP_LANG_STORAGE_KEY[^;]+;/);
  assert.ok(a >= 0 && b > a && c >= 0 && d > c && constants);
  const serverConstant = text.match(/const SERVER_LANGUAGE[^;]+;/); assert.ok(serverConstant);
  vm.runInContext(serverConstant[0] + constants[0] + text.slice(a, b) + text.slice(c, d), h.context);
  return h;
}
for (const [urlLang, stored] of [['zh', 'en'], ['en', 'zh']]) {
  test('mobile source getter explicit URL ' + urlLang + ' beats stored ' + stored, () => {
    const h = mobileLocaleContext('https://bookrank.test/new-books?lang=' + urlLang, stored, stored);
    assert.equal(vm.runInContext('getSavedLanguage()', h.context), urlLang);
  });
}
for (const [from, to] of [['zh', 'en'], ['en', 'zh']]) {
  test('mobile real setter ' + from + ' to ' + to + ' updates next lang retaining filters/view/page/return/hash', () => {
    const start = new URL('https://bookrank.test/new-books?lang=' + from + '&view=list&page=3&search=rain%20%26%20snow&publication_status=pending&return_to=%2Fawards%3Flang%3Dzh%26page%3D2#intro');
    const h = mobileLocaleContext(start.href, from, from);
    vm.runInContext('switchLanguage(' + JSON.stringify(to) + ')', h.context);
    const redirect = h.url(); assert.equal(redirect.pathname, '/set-language'); assert.equal(redirect.searchParams.get('lang'), to);
    const next = new URL(redirect.searchParams.get('next'), start.origin); assert.equal(next.searchParams.get('lang'), to);
    for (const key of ['view', 'page', 'search', 'publication_status', 'return_to']) assert.equal(next.searchParams.get(key), start.searchParams.get(key));
    assert.equal(next.hash, '#intro'); assert.equal(next.pathname, '/new-books');
  });
}
test('mobile source getter ignores invalid URL locale and retains normal stored/server fallback', () => {
  assert.equal(vm.runInContext('getSavedLanguage()', mobileLocaleContext('https://bookrank.test/?lang=bad', 'en', 'zh').context), 'en');
  assert.equal(vm.runInContext('getSavedLanguage()', mobileLocaleContext('https://bookrank.test/?lang=bad', '', 'zh').context), 'zh');
});
test('shared BookI18n renders raw numeric/currency prices and source group labels before empty-store return', () => {
  const h = harness();
  const raw = ['29.99', '0', '  $29.99  ', 'GBP 8.50'];
  const nodes = raw.map(value => { const node = new DomNode('span'); node.setAttribute('data-price-raw', value); return node; });
  const group = new DomNode('optgroup'); group.setAttribute('data-source-group-zh', '数据提供方'); group.setAttribute('data-source-group-en', 'Data providers');
  h.selectors.set('[data-price-raw]', nodes); h.selectors.set('optgroup[data-source-group-zh]', [group]);
  vm.runInContext(source('static/js/book-i18n.js'), h.context);
  const api = h.window.BookI18n;
  api.applyLanguage('zh'); assert.deepEqual(nodes.map(node => node.textContent), ['29.99（币种未确认）', '0（币种未确认）', '  $29.99  ', 'GBP 8.50']);
  assert.equal(group.getAttribute('label'), '数据提供方');
  api.applyLanguage('en'); assert.deepEqual(nodes.map(node => node.textContent), ['29.99 (currency unconfirmed)', '0 (currency unconfirmed)', '  $29.99  ', 'GBP 8.50']);
  assert.equal(group.getAttribute('label'), 'Data providers');
  assert.equal(api.formatPriceDisplay(0, 'zh'), '0（币种未确认）'); assert.equal(api.formatPriceDisplay('1e2', 'en'), '1e2 (currency unconfirmed)');
  assert.equal(api.formatPriceDisplay('   ', 'en'), '');
});
test('native detail links follow real manual language setter and popstate without changing external links', () => {
  const h = harness('https://bookrank.test/new-books?lang=zh&view=list&page=3&publication_status=pending&search=rain');
  const links = ['/new-book/7?return_to=%2Fnew-books%3Flang%3Dzh', '/award-book/9?lang=zh', '/book/2?category=fiction', 'https://external.test/book/2', '/profile'].map(href => { const node = new DomNode('a'); node.setAttribute('href', href); return node; });
  links[0].setAttribute('data-href', links[0].getAttribute('href'));
  h.selectors.set('a[href]', links);
  const reloadLink = new DomNode('a'); reloadLink.setAttribute('href', '/new-books?lang=zh'); h.ids.set('curated-refresh-link', reloadLink);
  h.context.localStorage = { getItem: () => 'zh', setItem() {} };
  h.context.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
  h.window.dispatchEvent = ev => h.window.fire(ev.type, ev);
  vm.runInContext(source('static/js/book-i18n.js'), h.context);
  vm.runInContext(source('static/js/translations.js'), h.context);
  h.document.fire('DOMContentLoaded');
  vm.runInContext("setGlobalLanguage('en')", h.context);
  const current = h.url().pathname + h.url().search;
  assert.equal(reloadLink.getAttribute('href'), current);
  for (const node of links.slice(0, 3)) {
    const detail = new URL(node.getAttribute('href'), h.url());
    assert.equal(detail.searchParams.get('return_to'), current); assert.equal(detail.searchParams.get('lang'), 'en');
  }
  assert.equal(links[0].getAttribute('data-href'), links[0].getAttribute('href'));
  assert.equal(new URL(links[2].getAttribute('href'), h.url()).searchParams.get('category'), 'fiction');
  assert.equal(links[3].getAttribute('href'), 'https://external.test/book/2'); assert.equal(links[4].getAttribute('href'), '/profile');
  h.window.location.href = '/new-books?lang=zh&view=grid&page=2&search=snow'; h.window.fire('popstate');
  assert.equal(reloadLink.getAttribute('href'), h.url().pathname + h.url().search);
  for (const node of links.slice(0, 3)) {
    const detail = new URL(node.getAttribute('href'), h.url());
    assert.equal(detail.searchParams.get('return_to'), h.url().pathname + h.url().search); assert.equal(detail.searchParams.get('lang'), 'zh');
  }
});
test('weekly comparison has no invented prior rank and magnitude is actual places rather than score', () => {
  const text = source('templates/weekly_report_detail.html');
  const start = text.indexOf("// {{ _('周榜对比图') }}");
  const end = text.indexOf('\n    }\n});', start); assert.ok(start >= 0 && end > start);
  const items = [
    { title: 'Gain', rank: 3, rank_change: 2 }, { title: 'Loss', rank: 5, rank_change: -3 },
    { title: 'New', rank: 2, rank_change: 0, is_new: true }, { title: 'Unknown', rank: 4, rank_change: null },
    { title: 'Stable', rank: 6, rank_change: 0 }, { title: 'Missing rank', rank: null, rank_change: 2 },
  ];
  const configs = [];
  const context = vm.createContext({ reportContent: { top_changes: items }, chartColors: {}, document: { getElementById: id => ({ getContext: () => id }) }, Chart: function(id, config) { configs.push({ id, config }); } });
  vm.runInContext(renderJinja(text.slice(start, end), {}), context);
  assert.equal(configs.length, 2);
  assert.deepEqual(Array.from(configs[0].config.data.datasets[1].data), [5, 2, null, null, 6, null]);
  assert.deepEqual(Array.from(configs[1].config.data.datasets[0].data), [2, 3, null, null, 0, null]);
  assert.equal(configs[1].config.options.scales.r.max, undefined);
  assert.equal(configs[1].config.data.datasets[0].label, '排名变化幅度（位）');
});
function renderErrorTemplate(name, context) {
  const translations = { '书籍不存在': 'Book not found', '该获奖图书已下架': 'Award book unavailable', '暂时无法加载': 'Temporarily unavailable', '书籍暂时无法加载，请稍后再试': 'Book could not be loaded. Please retry.', '获奖图书暂时无法加载，请稍后再试': 'Award book could not be loaded. Please retry.', '榜单暂时无法加载，请稍后再试': 'Charts could not be loaded. Please retry.', '周报加载失败，请稍后再试': 'Weekly report could not be loaded. Please retry.', '出错了': 'Error' };
  const code = "import json,sys; from jinja2 import Environment,DictLoader; sys.stdout.reconfigure(encoding='utf-8'); sys.stdin.reconfigure(encoding='utf-8'); x=json.load(sys.stdin); base='{% block title %}{% endblock %}{% block header %}{% endblock %}{% block content %}{% endblock %}'; e=Environment(loader=DictLoader({'source':x['source'],'base.html':base,'mobile/base.html':base})); e.globals['_']=lambda s:x['translations'].get(s,s); e.globals['csp_nonce']=lambda:'TEST'; print(e.get_template('source').render(**x['context']))";
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', code], { input: JSON.stringify({ source: source(name), translations, context }), encoding: 'utf8' });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr); return parseMarkup(result.stdout);
}
for (const name of ['templates/error.html', 'templates/mobile/error.html']) {
  test(name + ' maps raw backend error messages in English and preserves specific return target', () => {
    const cases = [['书籍不存在', 'Book not found'], ['该获奖图书已下架', 'Award book unavailable'], ['书籍暂时无法加载，请稍后再试', 'Temporarily unavailable'], ['获奖图书暂时无法加载，请稍后再试', 'Temporarily unavailable'], ['榜单暂时无法加载，请稍后再试', 'Temporarily unavailable'], ['周报加载失败，请稍后再试', 'Temporarily unavailable']];
    for (const [message, expected] of cases) {
      const dom = renderErrorTemplate(name, { message, heading: message, back_url: '/new-books?lang=en&view=list&page=3' });
      assert.equal(dom.querySelector('h1').textContent.trim(), expected);
      const messageNode = dom.querySelector(name.includes('/mobile/') ? '.m-error-message' : '.error-message'); assert.ok(messageNode);
      assert.equal(messageNode.textContent.includes(message), false);
      const links = dom.querySelectorAll('a'); assert.ok(links.some(link => link.getAttribute('href') === '/new-books?lang=en&view=list&page=3'));
    }
    const dom = renderErrorTemplate(name, { message: 'other failure', heading: 'Custom heading', back_url: '/' });
    assert.equal(dom.querySelector('h1').textContent, 'Custom heading');
  });
}
test('weekly real chart blocks distinguish gain/loss/new/unknown/stable without ordinal line', () => {
  const text = source('templates/weekly_report_detail.html');
  const start = text.indexOf('const chartColors'); assert.ok(start >= 0);
  const cat = text.indexOf("// {{ _('类别分布饼图') }}", start); assert.ok(cat > start);
  const first = text.slice(text.indexOf('if (reportContent.top_changes', start), cat);
  const comparison = text.indexOf("// {{ _('周榜对比图') }}", cat); assert.ok(comparison > cat);
  const trend = text.slice(text.indexOf('if (reportContent.top_changes', cat), comparison);
  const content = { top_changes: [
    { title: 'Gain', rank_change: 2 }, { title: 'Loss', rank_change: -3 },
    { title: 'New', rank_change: 0, is_new: true }, { title: 'Unknown', rank_change: null },
    { title: 'Stable', rank_change: 0, is_new: false },
  ] };
  const configs = [];
  const context = vm.createContext({ reportContent: content, chartColors: { green: 'green', red: 'red', gray: 'gray' }, document: { getElementById: id => ({ getContext: () => id }) }, Chart: function(id, config) { configs.push({ id, config }); } });
  vm.runInContext(renderJinja(first + trend, {}), context);
  assert.equal(configs.length, 2);
  for (const { config } of configs) {
    assert.equal(config.type, 'bar'); assert.equal(config.options.scales.y.beginAtZero, true);
    assert.deepEqual(Array.from(config.data.datasets[0].data), [2, -3, null, null, 0]);
    assert.equal(config.data.labels[2].includes('新上榜'), true); assert.equal(config.data.labels[3].includes('变化不可得'), true);
    const label = config.options.plugins.tooltip.callbacks.label;
    assert.equal(label({ dataIndex: 2, raw: null }), '新上榜'); assert.equal(label({ dataIndex: 3, raw: null }), '变化不可得');
    assert.equal(label({ dataIndex: 4, raw: 0 }), '无变化');
  }
});

function mobileInitialization(url, stored, cookieLang, server) {
  const h = harness(url); const markup = parseMarkup(source('templates/mobile/base.html'));
  for (const node of markup.querySelectorAll('button').concat(markup.querySelectorAll('div'))) if (node.id) h.ids.set(node.id, node);
  const dropdown = h.ids.get('m-lang-dropdown'); assert.ok(dropdown, 'actual mobile base contains language dropdown');
  const menuButtons = dropdown.querySelectorAll('button').filter(node => node.getAttribute('data-lang'));
  assert.equal(menuButtons.length, 2); dropdown.querySelectorAll = selector => selector === 'button[data-lang]' ? menuButtons : [];
  h.selectors.set('#m-lang-dropdown button[data-lang]', menuButtons);
  for (const node of menuButtons.concat([dropdown, h.ids.get('m-lang-globe')])) node.classList.toggle = (name, force) => { const on = force === undefined ? !node.classList.contains(name) : force; if (on) node.classList.add(name); else node.classList.remove(name); return on; };
  h.document.documentElement = new DomNode('html'); h.document.documentElement.setAttribute('data-lang', server); h.document.documentElement.setAttribute('lang', server === 'en' ? 'en' : 'zh-CN');
  h.document.readyState = 'loading'; h.document.body = new DomNode('body'); h.document.createElement = tag => new DomNode(tag);
  const values = new Map([['app_language', stored], ['bookrank_language', stored]]); const jar = new Map([['lang', cookieLang], ['unrelated_preference', 'unchanged']]); const writes = [];
  Object.defineProperty(h.document, 'cookie', { get() { return [...jar].map(([key, value]) => key + '=' + value).join('; '); }, set(value) { writes.push(value); const [pair] = value.split(';'); const equal = pair.indexOf('='); jar.set(pair.slice(0, equal), pair.slice(equal + 1)); } });
  h.context.localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  h.context.CustomEvent = class { constructor(type, init) { this.type = type; this.detail = init.detail; } };
  h.window.dispatchEvent = ev => h.window.fire(ev.type, ev); h.context.setInterval = () => { throw new Error('base-only page must not start polling'); };
  h.context.fetch = () => { throw new Error('language initialization must not issue API requests'); };
  vm.runInContext(source('static/mobile/js/mobile.js'), h.context); h.document.fire('DOMContentLoaded');
  const profile = markup.querySelectorAll('a').find(node => node.getAttribute('href') === '/profile'); assert.ok(profile, 'actual mobile base favorites navigation is /profile');
  return { h, values, jar, writes, profile };
}
for (const [lang, old] of [['zh', 'en'], ['en', 'zh']]) test(`mobile full initialization persists explicit ${lang} for bare favorites navigation`, () => {
  const f = mobileInitialization('https://bookrank.test/awards?lang=' + lang + '&search=James&view=list', old, old, lang);
  assert.equal(f.values.get('app_language'), lang); assert.equal(f.values.get('bookrank_language'), lang);
  assert.equal(f.jar.get('lang'), lang, 'explicit URL locale must update stale existing language cookie before bare /profile navigation');
  assert.equal(f.jar.get('unrelated_preference'), 'unchanged'); assert.equal(f.profile.getAttribute('href'), '/profile');
  assert.equal(f.h.url().pathname, '/awards'); assert.equal(f.h.url().searchParams.get('search'), 'James'); assert.equal(f.h.url().searchParams.get('view'), 'list');
  assert.equal(f.writes.length, 1); assert.match(f.writes[0], /path=\//i); assert.match(f.writes[0], /SameSite=Lax/i); assert.match(f.writes[0], /max-age=31536000/i);
});
test('mobile full initialization invalid or absent URL locale leaves valid cookie preference intact', () => {
  for (const query of ['?lang=bad', '']) {
    const f = mobileInitialization('https://bookrank.test/awards' + query, 'en', 'en', 'en');
    assert.equal(f.jar.get('lang'), 'en'); assert.equal(f.values.get('app_language'), 'en'); assert.equal(f.writes.length, 0);
  }
});
for (const [name, cls] of [['templates/weekly_report_detail.html', 'recommendation-reason'], ['templates/mobile/weekly_report_detail.html', 'm-report-rec-reason']]) {
  test(name + ' recommendation reason renders facts without unverifiable marketing', () => {
    const text = source(name); const start = text.indexOf('<div class="' + cls + '"'); assert.ok(start >= 0);
    const end = text.indexOf('</div>', start); assert.ok(end > start);
    const html = renderJinja(text.slice(start, end + 6), { book: { category: 'Fiction', rank: 3, weeks_on_list: 8, rank_change: 2, is_new: false, reason: '不可证实营销断言', description: '更长营销简介' } });
    const dom = parseMarkup(html);
    const rendered = dom.querySelector('.' + cls).textContent;
    assert.equal(rendered.includes('不可证实营销断言'), false); assert.equal(rendered.includes('更长营销简介'), false);
    assert.equal(rendered.includes('3'), true); assert.equal(rendered.includes('8'), true); assert.equal(rendered.includes('2'), true);
  });
}
