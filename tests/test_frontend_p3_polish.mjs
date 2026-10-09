import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import { transformSync } from 'esbuild';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = name => readFileSync(path.join(repo, name), 'utf8').replace(/\r\n/g, '\n');
function render(name, context, locale = 'en') {
  const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root: repo, name, context, locale, url: '/?lang=' + locale, actual_display_labels: true }),
    encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
const hasClass = (node, name) => (node.attrs.class || '').split(/\s+/).includes(name);
const within = (result, node, ancestor) => node.ancestors.includes(result.nodes.indexOf(ancestor));
const report = { title: '历史周报', week_start: '2026-09-21', week_end: '2026-09-27', report_date: '2026-09-27', created_at: '2026-09-28T12:34:00', updated_at: null, content_data: { title_display: 'Weekly Bestseller Report', summary: 'Summary' } };
const newBook = { id: 7, title: 'A Complete Original Book Title: With Its Subtitle', title_zh: '简称', author: 'Writer', cover_url: '', description: 'Description.', description_zh: '', publication_date: null, category: '小说', publisher: null, isbn13: '9780306406157', page_count: null, language: 'en', price: null, buy_links: [] };
const newList = books => ({ books, stats: {}, publishers: [], categories: [], selected_days: 30, future_preview_days: 14, selected_category: '', selected_publisher: '', selected_publication_status: 'all', search_query: '', data_load_failed: false, total: books.length, page: 1, total_pages: 1 });
const weeklyBook = { title: 'The Complete Original Book Title: A Very Important Subtitle', title_zh: '译名简称', author: 'Writer', category: '精装小说', cover: '/cache/images/actual.jpg', rank: 2, rank_change: 3, weeks_on_list: 12, is_new: false };
const weeklyContent = { title_display: 'Weekly Bestseller Report', top_changes: [weeklyBook], new_books: [weeklyBook], top_risers: [weeklyBook], longest_running: [weeklyBook], featured_books: [weeklyBook], category_stats: {}, total_books: 10 };

test('mobile rendered assets preserve the search CSS version and refresh the full-audit JS version in both locales', () => {
  for (const locale of ['en', 'zh']) {
    const result = render('mobile/new_books.html', newList([]), locale);
    const urls = result.nodes.flatMap(node => {
      const value = node.tag === 'link' ? node.attrs.href : node.tag === 'script' ? node.attrs.src : null;
      if (!value) return [];
      const url = new URL(value, 'https://bookrank.example');
      return ['/static/mobile/css/mobile.css', '/static/mobile/js/mobile.js'].includes(url.pathname) ? [url] : [];
    });
    assert.equal(urls.length, 2);
    const expectedVersions = new Map([
      ['/static/mobile/css/mobile.css', 'mobile-search-320-20261009'],
      ['/static/mobile/js/mobile.js', 'full-audit-20261009'],
    ]);
    assert.deepEqual(urls.map(url => url.pathname).sort(), [...expectedVersions.keys()].sort());
    for (const url of urls) assert.equal(url.searchParams.get('v'), expectedVersions.get(url.pathname));
  }
});

test('mobile weekly full title owners wrap the original instead of clipping it behind an ellipsis', () => {
  const css = transformSync(source('static/mobile/css/mobile.css'), { loader: 'css', minifyWhitespace: true, legalComments: 'none' }).code;
  for (const selector of ['.m-report-change-title', '.m-report-rec-title']) {
    const styles = new Map();
    for (const block of css.split('}')) {
      const boundary = block.lastIndexOf('{');
      if (!block.slice(0, boundary).trim().split(',').map(value => value.trim()).includes(selector)) continue;
      for (const value of block.slice(boundary + 1).split(';')) {
        const colon = value.indexOf(':'); if (colon > 0) styles.set(value.slice(0, colon).trim(), value.slice(colon + 1).trim());
      }
    }
    assert.equal(styles.get('white-space'), 'normal'); assert.equal(styles.get('overflow'), 'visible');
    assert.equal(styles.get('text-overflow'), 'clip'); assert.equal(styles.get('min-width'), '0');
    assert.equal(styles.get('overflow-wrap'), 'anywhere');
  }
  // Actual CSS owner constraints, not a substitute for narrow viewport browser acceptance.
});

for (const locale of ['zh', 'en']) {
  for (const [template, context] of [
    ['mobile/new_books.html', newList([])],
    ['mobile/weekly_reports.html', { reports: [report], latest_report: report, report_sections: [{ year: 2026, month: 9, reports: [report] }], is_generating: false }],
    ['mobile/weekly_report_detail.html', { report, content: weeklyContent, safe_summary: '' }],
    ['mobile/profile.html', { favorites: [], search_history: [], reading_history: [] }],
  ]) {
    test(`${template} has one visible meaningful h1 in ${locale}`, () => {
      const result = render(template, context, locale);
      const headings = result.nodes.filter(node => node.tag === 'h1');
      assert.equal(headings.length, 1);
      assert.ok(headings[0].text.trim());
      assert.doesNotMatch(headings[0].attrs.class || '', /sr-only/);
      assert.equal(Object.hasOwn(headings[0].attrs, 'hidden'), false);
    });
  }
}

for (const cover of ['', null, '/static/default-cover.png', '/cache/images/real-cover.jpg']) {
  for (const template of ['mobile/new_books.html', 'mobile/new_book_detail.html']) {
    test(`${template} preserves a real cover and renders a neutral absent-cover state (${String(cover)})`, () => {
      const book = { ...newBook, cover_url: cover };
      const result = render(template, template.includes('new_books') ? newList([book]) : { book, back_url: '/new-books?lang=en' });
      const owner = result.nodes.find(node => hasClass(node, template.includes('new_books') ? 'm-book-card' : 'm-book-detail'));
      assert.ok(owner);
      const images = result.nodes.filter(node => node.tag === 'img' && within(result, node, owner));
      if (cover && !cover.includes('default-cover')) {
        assert.equal(images.length, 1); assert.equal(images[0].attrs.src, cover);
        assert.ok(Object.hasOwn(images[0].attrs, 'data-neutral-cover'));
        assert.equal(Object.hasOwn(images[0].attrs, 'data-cover-fallback'), false);
      } else {
        assert.equal(images.length, 0, 'missing covers must not use the building photo');
        assert.ok(owner.text.includes('No cover'));
      }
    });
  }
}

test('new-book neutral fallback handles both already-failed images and captured error events without changing other fallbacks', () => {
  const code = source('static/mobile/js/mobile.js');
  const start = code.indexOf('    const COVER_FALLBACK');
  const end = code.indexOf('    // ===== 4b.', start); assert.ok(start >= 0 && end > start);
  const handlers = {};
  function image(neutral, complete = false) {
    const placeholder = { hidden: true, style: { display: 'none' }, textContent: 'No cover', classList: { contains: name => name === 'm-neutral-cover-placeholder' } };
    return { tagName: 'IMG', dataset: {}, src: '/cache/images/broken.jpg', style: {}, complete, naturalWidth: 0,
      hidden: false, hasAttribute: name => name === (neutral ? 'data-neutral-cover' : 'data-cover-fallback'),
      parentElement: { querySelector: () => placeholder }, nextElementSibling: placeholder,
      closest: () => ({ querySelector: () => placeholder }), placeholder };
  }
  const failed = image(true, true); const eventImage = image(true); const legacy = image(false);
  vm.runInNewContext(code.slice(start, end) + '\ninitImageFallback();', {
    document: { addEventListener(type, fn, capture) { handlers[type] = fn; if (type === 'error') assert.equal(capture, true); }, querySelectorAll: selector => selector.includes('data-neutral-cover') ? [failed, eventImage] : [legacy] }, window: {},
  });
  assert.ok(failed.hidden || failed.style.display === 'none');
  assert.ok(!failed.placeholder.hidden || failed.placeholder.style.display !== 'none');
  handlers.error({ target: eventImage });
  assert.ok(eventImage.hidden || eventImage.style.display === 'none');
  assert.ok(!eventImage.placeholder.hidden || eventImage.placeholder.style.display !== 'none');
  assert.notEqual(eventImage.src, '/static/default-cover.png');
  handlers.error({ target: legacy }); assert.equal(legacy.src, '/static/default-cover.png');
});

test('profile real empty-state search remains a GET with locale and a shrinkable 44px submit row', () => {
  const result = render('mobile/profile.html', { favorites: [], search_history: [], reading_history: [] });
  const input = result.nodes.find(node => node.attrs.id === 'mobile-profile-search-input');
  const form = result.nodes.find(node => node.tag === 'form' && within(result, input, node)); assert.ok(form);
  assert.equal(form.attrs.action, '/'); assert.equal(form.attrs.method, 'get'); assert.equal(input.attrs.name, 'search');
  const locale = result.nodes.find(node => node.attrs.name === 'lang' && within(result, node, form)); assert.equal(locale.attrs.value, 'en');
  const button = result.nodes.find(node => node.tag === 'button' && within(result, node, form)); assert.equal(button.attrs.type, 'submit');
  assert.match(input.attrs.style || '', /min-width\s*:\s*0/);
  assert.match(input.attrs.style || '', /flex\s*:\s*1/);
  assert.match(button.attrs.style || '', /min-height\s*:\s*44px/);
  assert.match(button.attrs.style || '', /flex-shrink\s*:\s*0/);
  assert.match(form.attrs.style || '', /width\s*:\s*100%/);
  assert.match(form.attrs.style || '', /box-sizing\s*:\s*border-box/);
  assert.match(form.attrs.style || '', /padding-inline\s*:\s*var\(--space-4\)/, 'the parent empty state overrides horizontal padding to zero; keep buttons inset from the viewport');
  // These source/SSR constraints are separate from browser geometry at 320/390.
});

test('profile search label remains accessible without taking flex-row space', () => {
  const result = render('mobile/profile.html', { favorites: [], search_history: [], reading_history: [] });
  const label = result.nodes.find(node => node.tag === 'label' && node.attrs.for === 'mobile-profile-search-input');
  assert.ok(label.text.includes('Search'));
  assert.equal(Object.hasOwn(label.attrs, 'hidden'), false);
  assert.notEqual(label.attrs['aria-hidden'], 'true');
  const css = transformSync(source('static/mobile/css/mobile.css'), { loader: 'css', minifyWhitespace: true, legalComments: 'none' }).code;
  const selector = '#m-favorites-empty .sr-only';
  const block = css.split('}').find(value => value.slice(0, value.lastIndexOf('{')).trim().split(',').map(value => value.trim()).includes(selector));
  assert.ok(block, 'mobile has no global sr-only utility; this profile label needs a scoped visual hiding rule');
  const styles = Object.fromEntries(block.slice(block.lastIndexOf('{') + 1).split(';').filter(Boolean).map(value => {
    const colon = value.indexOf(':'); return [value.slice(0, colon), value.slice(colon + 1)];
  }));
  assert.equal(styles.position, 'absolute'); assert.equal(styles.width, '1px'); assert.equal(styles.height, '1px');
  assert.equal(styles.overflow, 'hidden'); assert.equal(styles['white-space'], 'nowrap');
  assert.notEqual(styles.display, 'none'); assert.notEqual(styles.visibility, 'hidden');
});

for (const template of ['weekly_report_detail.html', 'mobile/weekly_report_detail.html']) {
  for (const locale of ['en', 'zh']) {
    test(`${template} book labels use full original titles and localized category/facts in ${locale}`, () => {
      const result = render(template, { report, content: weeklyContent, safe_summary: '' }, locale);
      const textClasses = template.startsWith('mobile') ? ['m-report-change-title', 'm-book-title', 'm-report-rec-title'] : ['change-title', 'book-title', 'recommendation-title'];
      const titles = result.nodes.filter(node => textClasses.some(name => hasClass(node, name))); assert.ok(titles.length >= 3);
      for (const node of titles) {
        assert.ok(node.text.includes(locale === 'en' ? weeklyBook.title : weeklyBook.title_zh));
        if (locale === 'en') assert.equal(node.text.includes(weeklyBook.title_zh), false);
      }
      const covers = result.nodes.filter(node => node.tag === 'img' && node.attrs.src.includes('actual.jpg')); assert.ok(covers.length);
      for (const image of covers) assert.ok(image.attrs.alt.includes(locale === 'en' ? weeklyBook.title : weeklyBook.title_zh));
      const reasons = result.nodes.filter(node => hasClass(node, template.startsWith('mobile') ? 'm-report-rec-reason' : 'recommendation-reason')); assert.equal(reasons.length, 1);
      if (locale === 'en') { assert.ok(reasons[0].text.includes('Hardcover Fiction')); assert.doesNotMatch(reasons[0].text, /小说|第|名|在榜|周|上升|位/); }
      else { assert.ok(result.nodes.some(node => hasClass(node, 'm-report-original-title') && node.text.includes(weeklyBook.title)) || titles.every(node => node.text.includes(weeklyBook.title)), 'Chinese presentation must retain the full original as well'); }
    });
  }
}

function element(tag) {
  return { tagName: tag.toUpperCase(), children: [], dataset: {}, attrs: {}, style: {}, listeners: {}, className: '', textContent: '',
    classList: { add() {}, remove() {}, contains() { return false; } },
    setAttribute(name, value) { this.attrs[name] = String(value); }, addEventListener(type, fn) { this.listeners[type] = fn; },
    appendChild(child) { child.parentElement = this; this.children.push(child); return child; },
    get firstChild() { return this.children[0]; }, removeChild(child) { this.children.splice(this.children.indexOf(child), 1); },
    querySelector() { return null; }, closest() { return this.parentElement; }, focus() {},
  };
}
const flush = async () => { for (let i = 0; i < 10; i++) await Promise.resolve(); };

function deferredAnalytics() {
  const result = render('analytics_dashboard.html', {}, 'zh');
  const code = result.nodes.find(node => node.tag === 'script' && node.text.includes('const chartColors')).text;
  const tbody = element('tbody'); tbody.id = 'top-reports-table';
  const parent = element('div'); parent.appendChild(tbody);
  parent.querySelector = selector => selector.includes('panel-status') ? parent.children.find(node => node.className === 'panel-status') || null : null;
  const pending = []; const languageHandlers = [];
  const walk = node => [node, ...(node.children || []).flatMap(walk)];
  const context = vm.createContext({ console: { error() {} }, URLSearchParams, encodeURIComponent,
    window: { __APP_LANG__: 'zh', addEventListener(type, fn) { if (type === 'languagechange') languageHandlers.push(fn); } },
    document: { documentElement: { getAttribute: () => 'zh' }, getElementById: id => id === tbody.id ? tbody : null,
      querySelectorAll: selector => selector === '[data-analytics-text]' ? walk(parent).filter(node => node.dataset?.analyticsText) : selector === '.panel-status' ? walk(parent).filter(node => node.className === 'panel-status') : [],
      addEventListener() {}, createElement: element, createTextNode: value => ({ textContent: value, children: [] }) },
    fetch: url => new Promise((resolve, reject) => pending.push({ url, resolve, reject })),
  });
  vm.runInContext(code, context);
  vm.runInContext('loadTopReportsPanel()', context);
  assert.equal(languageHandlers.length, 1);
  function switchLanguage(locale) { context.window.__APP_LANG__ = locale; languageHandlers[0](); }
  function success(index, title, date = '2026-10-04') {
    pending[index].resolve({ ok: true, json: async () => ({ success: true, data: [{ date, title: '原始标题', title_display: title, view_count: 23 }] }) });
  }
  const statuses = () => parent.children.filter(node => node.className === 'panel-status');
  return { tbody, pending, context, switchLanguage, success, statuses };
}

for (const failCurrentRequest of [false, true]) {
  test(`analytics retained View link follows current locale while replacement request ${failCurrentRequest ? 'fails' : 'is pending'}`, async () => {
    const f = deferredAnalytics(); f.success(0, '纽约时报畅销书周报'); await flush();
    const row = f.tbody.children[0]; const link = row.children[3].children[0];
    link.href += '&source=top10&return_to=%2Freports%3Fmonth%3D9#book';
    const before = new URL(link.href, 'https://bookrank.example');
    const facts = row.children.slice(0, 3).map(cell => cell.textContent);
    f.switchLanguage('en');
    assert.equal(f.pending.length, 2);
    if (failCurrentRequest) {
      f.pending[1].reject(new Error('current English query unavailable')); await flush();
      assert.ok(f.statuses().some(node => node.dataset.statusKind === 'error'));
    } else assert.ok(f.statuses().some(node => node.dataset.statusKind === 'loading'));
    const after = new URL(link.href, 'https://bookrank.example');
    assert.equal(link.textContent, 'View');
    assert.equal(after.searchParams.get('lang'), 'en', 'retained active links must match current locale before a successful replacement response');
    assert.equal(after.origin, before.origin); assert.equal(after.pathname, before.pathname);
    assert.equal(after.searchParams.get('source'), before.searchParams.get('source'));
    assert.equal(after.searchParams.get('return_to'), before.searchParams.get('return_to'));
    assert.equal(after.hash, before.hash);
    assert.equal(f.tbody.children[0], row, 'keep available factual data while a replacement is pending or fails');
    assert.deepEqual(row.children.slice(0, 3).map(cell => cell.textContent), facts);
  });
}

for (const staleFailure of [false, true]) {
  test(`analytics stale locale ${staleFailure ? 'failure' : 'success'} cannot overwrite the latest English result or status`, async () => {
    const f = deferredAnalytics(); f.switchLanguage('en');
    assert.equal(f.pending.length, 2, 'only Top10 is refetched when language changes');
    assert.equal(new URL(f.pending[0].url, 'https://bookrank.example').searchParams.get('lang'), 'zh');
    assert.equal(new URL(f.pending[1].url, 'https://bookrank.example').searchParams.get('lang'), 'en');
    f.success(1, 'NYT Weekly Bestseller Report'); await flush();
    assert.equal(f.tbody.children[0].children[1].textContent, 'NYT Weekly Bestseller Report');
    if (staleFailure) f.pending[0].reject(new Error('obsolete locale failed'));
    else f.success(0, '纽约时报畅销书周报');
    await flush();
    assert.equal(f.tbody.children[0].children[1].textContent, 'NYT Weekly Bestseller Report');
    assert.equal(new URL(f.tbody.children[0].children[3].children[0].href, 'https://bookrank.example').searchParams.get('lang'), 'en');
    assert.ok(f.statuses().every(node => !node.dataset.statusKind), 'stale outcomes must not display an error or loading state');
  });
}

test('analytics latest request generation owns the loading state even after switching back to the same locale', async () => {
  const f = deferredAnalytics(); f.switchLanguage('en'); f.switchLanguage('zh');
  assert.equal(f.pending.length, 3);
  f.success(0, 'Obsolete Chinese response'); await flush();
  assert.equal(f.tbody.children.length, 0, 'same-locale stale response still belongs to an obsolete generation');
  assert.ok(f.statuses().every(node => node.dataset.statusKind === 'loading'));
  f.pending[1].reject(new Error('obsolete English response failed')); await flush();
  assert.ok(f.statuses().every(node => node.dataset.statusKind === 'loading'));
  f.success(2, '当前中文周报'); await flush();
  assert.equal(f.tbody.children[0].children[1].textContent, '当前中文周报');
  assert.equal(new URL(f.tbody.children[0].children[3].children[0].href, 'https://bookrank.example').searchParams.get('lang'), 'zh');
  assert.ok(f.statuses().every(node => !node.dataset.statusKind));
});

test('analytics actual script requests current locale, uses optional title_display safely and keeps locale on detail links', async () => {
  for (const locale of ['en', 'zh']) {
    const result = render('analytics_dashboard.html', {}, locale);
    const code = result.nodes.find(node => node.tag === 'script' && node.text.includes('const chartColors')).text;
    const tbody = element('tbody'); tbody.id = 'top-reports-table'; const parent = element('div'); parent.appendChild(tbody);
    const calls = []; const languageHandlers = [];
    const context = vm.createContext({ console: { error() {} }, URLSearchParams, encodeURIComponent,
      window: { __APP_LANG__: locale, addEventListener(type, fn) { if (type === 'languagechange') languageHandlers.push(fn); } },
      document: { documentElement: { getAttribute: () => locale }, getElementById: id => id === tbody.id ? tbody : null, querySelectorAll: () => [], addEventListener() {}, createElement: element },
      fetch: async url => { calls.push(url); return { ok: true, json: async () => ({ success: true, data: [
        { date: '2026-09-27', title: '原始标题', title_display: '<img src=x onerror=alert(1)>', view_count: 7 },
        { date: '2026-09-20', title: 'Legacy title', view_count: 2 },
        { date: '2026-09-13', title: 'Fallback', title_display: null, view_count: 1 },
        { date: '2026-09-06', title: 'Must not replace an explicit empty display title', title_display: '', view_count: 0 },
      ] }) }; },
    });
    vm.runInContext(code, context); vm.runInContext('loadTopReportsPanel()', context); await flush();
    assert.equal(new URL(calls[0], 'https://bookrank.example').searchParams.get('lang'), locale);
    assert.equal(tbody.children[0].children[1].textContent, '<img src=x onerror=alert(1)>'); assert.equal(tbody.children[0].children[1].children.length, 0);
    assert.equal(tbody.children[1].children[1].textContent, 'Legacy title'); assert.equal(tbody.children[2].children[1].textContent, 'Fallback');
    assert.equal(tbody.children[3].children[1].textContent, '');
    for (const row of tbody.children) assert.equal(new URL(row.children[3].children[0].href, 'https://bookrank.example').searchParams.get('lang'), locale);
    context.window.__APP_LANG__ = locale === 'en' ? 'zh' : 'en';
    assert.equal(languageHandlers.length, 1); languageHandlers[0](); await flush();
    assert.equal(new URL(calls.at(-1), 'https://bookrank.example').searchParams.get('lang'), context.window.__APP_LANG__);
    for (const row of tbody.children) assert.equal(new URL(row.children[3].children[0].href, 'https://bookrank.example').searchParams.get('lang'), context.window.__APP_LANG__);
  }
});

function weeklyModal(locale, book = weeklyBook) {
    const content = { ...weeklyContent, featured_books: [book] };
    const result = render('weekly_report_detail.html', { report, content, safe_summary: '' }, locale);
    const raw = result.nodes.find(node => node.tag === 'script' && node.text.includes('const reportContent =')).text;
    const end = raw.indexOf('    // ', raw.indexOf('modalClose.addEventListener')); assert.ok(end > 0);
    const code = raw.slice(0, end) + '\n});';
    const owner = result.nodes.find(node => hasClass(node, 'recommendation-card')); assert.ok(owner);
    const card = element('div'); for (const [key, value] of Object.entries(owner.attrs)) if (key.startsWith('data-')) card.dataset[key.slice(5).replace(/-([a-z])/g, (_, char) => char.toUpperCase())] = value;
    const button = element('button'); button.closest = () => card;
    const close = element('button'); const body = element('div'); const overlay = element('dialog'); overlay.showModal = () => {}; overlay.querySelector = selector => selector === '.weekly-modal-close' ? close : body;
    let ready;
    vm.runInNewContext(code, { console, fetch: async () => ({}), window: { addEventListener() {} },
      document: { body: { style: {}, appendChild() {} }, addEventListener(type, fn) { if (type === 'DOMContentLoaded') ready = fn; },
        querySelectorAll: selector => selector === '.book-detail-btn' ? [button] : [], createElement(tag) {
          if (tag === 'dialog') return overlay;
          const node = element(tag);
          Object.defineProperty(node, 'innerHTML', { get() { return this.textContent.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); } });
          return node;
        } },
    });
    ready(); button.listeners.click.call(button);
    return body.innerHTML;
}

test('desktop weekly real detail handler presents the localized full title and category in the modal', () => {
  for (const locale of ['en', 'zh']) {
    const html = weeklyModal(locale);
    assert.ok(html.includes(weeklyBook.title));
    if (locale === 'en') { assert.ok(html.includes('Hardcover Fiction')); assert.doesNotMatch(html, /译名简称|小说/); }
    else assert.ok(html.includes(weeklyBook.title_zh));
  }
});

for (const [initialLocale, switchedLocale] of [['zh', 'en'], ['en', 'zh']]) {
  test(`weekly real setGlobalLanguage history update forces a new SSR document when the URL hash already matches (${initialLocale} to ${switchedLocale})`, () => {
    const result = render('weekly_report_detail.html', { report, content: weeklyContent, safe_summary: '' }, initialLocale);
    const sync = result.nodes.find(node => node.tag === 'script' && node.text.includes('var ssrLang = canonical('));
    const translations = source('static/js/translations.js');
    const start = translations.indexOf('function setGlobalLanguage(');
    const end = translations.indexOf('// 暴露到全局', start); assert.ok(start >= 0 && end > start);
    let currentHref = `https://bookrank.example/reports/weekly/2026-09-27?lang=${initialLocale}&view=compact#recommendations`;
    const handlers = []; const documentRequests = []; const sameDocumentTargets = []; const sequence = [];
    const location = {
      get href() { return currentHref; }, get hostname() { return new URL(currentHref).hostname; },
      replace(value) {
        const target = new URL(value, currentHref); const current = new URL(currentHref);
        if (target.origin === current.origin && target.pathname === current.pathname && target.search === current.search && target.hash) sameDocumentTargets.push(target.href);
        else documentRequests.push({ type: 'replace', url: target.href });
        currentHref = target.href;
      },
      reload() { documentRequests.push({ type: 'reload', url: currentHref }); },
    };
    const html = { lang: initialLocale, getAttribute(name) { return name === 'lang' ? this.lang : null; } };
    const context = vm.createContext({ URL, console, localStorage: { setItem() {} },
      history: { replaceState(_state, _title, value) { currentHref = new URL(value, currentHref).href; sequence.push('history'); } },
      CustomEvent: class { constructor(type, options) { this.type = type; this.detail = options.detail; } },
      applyPageTranslation() {},
      window: { location, __APP_LANG__: initialLocale,
        addEventListener(type, fn) { if (type === 'languagechange') handlers.push(fn); },
        dispatchEvent(event) { sequence.push('event'); for (const handler of handlers) handler(event); },
      },
      document: { documentElement: html, getElementById: () => null },
    });
    vm.runInContext(sync.text, context); vm.runInContext(translations.slice(start, end), context);
    vm.runInContext(`setGlobalLanguage('${initialLocale}')`, context); assert.equal(documentRequests.length, 0);
    sequence.length = 0;
    vm.runInContext(`setGlobalLanguage('${switchedLocale}')`, context);
    assert.deepEqual(sequence, ['history', 'event'], 'execute the actual production history-before-languagechange order');
    assert.equal(documentRequests.length, 1, 'same-document replace with an existing hash does not refresh server-rendered cards');
    assert.equal(documentRequests[0].type, 'reload'); assert.equal(sameDocumentTargets.length, 0);
    const target = new URL(documentRequests[0].url);
    assert.equal(target.origin, 'https://bookrank.example'); assert.equal(target.pathname, '/reports/weekly/2026-09-27');
    assert.equal(target.searchParams.get('lang'), switchedLocale); assert.equal(target.searchParams.get('view'), 'compact'); assert.equal(target.hash, '#recommendations');
    vm.runInContext(`setGlobalLanguage('${switchedLocale}')`, context); assert.equal(documentRequests.length, 1, 'keep navigation guard until the new SSR response loads');
    const refreshed = render('weekly_report_detail.html', { report, content: weeklyContent, safe_summary: '' }, target.searchParams.get('lang'));
    assert.ok(refreshed.nodes.find(node => hasClass(node, 'recommendation-title')).text.includes(switchedLocale === 'en' ? weeklyBook.title : weeklyBook.title_zh));
  });

  test(`weekly actual SSR language sync preserves report conditions and renders switched cards/modal (${initialLocale} to ${switchedLocale})`, () => {
    const result = render('weekly_report_detail.html', { report, content: weeklyContent, safe_summary: '' }, initialLocale);
    const sync = result.nodes.find(node => node.tag === 'script' && node.text.includes('var ssrLang = canonical('));
    assert.ok(sync, 'the modal-only source VM must not omit the actual page language navigation script');
    const handlers = []; const targets = [];
    const originalUrl = `https://bookrank.example/reports/weekly/2026-09-27?lang=${initialLocale}&view=compact&category=fiction#recommendations`;
    vm.runInNewContext(sync.text, { URL,
      window: { location: { href: originalUrl, replace: value => targets.push(value) }, addEventListener(type, fn) { if (type === 'languagechange') handlers.push(fn); } },
      document: { documentElement: { getAttribute: () => initialLocale } },
    });
    assert.equal(handlers.length, 1);
    handlers[0]({ detail: { language: initialLocale } }); assert.equal(targets.length, 0);
    handlers[0]({ detail: { language: switchedLocale } }); assert.equal(targets.length, 1);
    const next = new URL(targets[0]); const before = new URL(originalUrl);
    assert.equal(next.origin, before.origin); assert.equal(next.pathname, before.pathname);
    assert.equal(next.searchParams.get('lang'), switchedLocale); assert.equal(next.searchParams.get('view'), 'compact');
    assert.equal(next.searchParams.get('category'), 'fiction'); assert.equal(next.hash, '#recommendations');
    handlers[0]({ detail: { language: switchedLocale } }); assert.equal(targets.length, 1, 'no repeated navigation loop');
    const localized = render('weekly_report_detail.html', { report, content: weeklyContent, safe_summary: '' }, next.searchParams.get('lang'));
    for (const node of localized.nodes.filter(node => ['change-title', 'book-title', 'recommendation-title'].some(name => hasClass(node, name)))) {
      assert.ok(node.text.includes(switchedLocale === 'en' ? weeklyBook.title : weeklyBook.title_zh));
      if (switchedLocale === 'en') assert.equal(node.text.includes(weeklyBook.title_zh), false);
    }
    const reason = localized.nodes.find(node => hasClass(node, 'recommendation-reason'));
    assert.ok(reason.text.includes(switchedLocale === 'en' ? 'Hardcover Fiction' : '精装小说'));
    const html = weeklyModal(switchedLocale);
    assert.ok(html.includes(switchedLocale === 'en' ? 'Up 3 places' : '上升 3 位'));
    if (switchedLocale === 'en') assert.doesNotMatch(html, /译名简称|小说/);
    else assert.ok(html.includes(weeklyBook.title));
  });
}

test('desktop weekly modal labels a decline as Down and retains the actual rank/weeks facts', () => {
  const html = weeklyModal('en', { ...weeklyBook, title: 'A Declining Book', rank: 5, rank_change: -3, weeks_on_list: 8 });
  assert.match(html, /Down 3 places/); assert.doesNotMatch(html, /Up 3/);
  assert.match(html, /Rank 5/); assert.match(html, /8 weeks on list/);
});

test('desktop weekly modal keeps hostile book title/author as escaped literal text', () => {
  const html = weeklyModal('en', { ...weeklyBook, title: '<img src=x onerror=alert(1)>', author: '<svg onload=alert(2)>' });
  assert.ok(html.includes('&lt;img src=x onerror=alert(1)&gt;')); assert.ok(html.includes('&lt;svg onload=alert(2)&gt;'));
  assert.doesNotMatch(html, /<img|<svg/);
});
