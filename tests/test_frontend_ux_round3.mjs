import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import vm from 'node:vm';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { transformSync } from 'esbuild';

const repo = process.env.ROUND3_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const source = name => fs.readFileSync(path.join(repo, name), 'utf8').replace(/\r\n/g, '\n');
function scripts(html) { return [...html.matchAll(/<script(?=[ \t\n\f\r/>])(?:[^>]*>)([\s\S]*?)<\/script(?=[ \t\n\f\r/>])[^>]*>/gi)].map(match => match[1]); }
function render(name, context = {}, url = '/?lang=zh', locale = 'zh') {
  const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root: repo, name, context, url, locale }), encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
const hasClass = (node, name) => (node.attrs.class || '').split(/\s+/).includes(name);
const ancestors = (result, node) => node.ancestors.map(index => result.nodes[index]);
// Inspect the actual unconditional owner rule; browser geometry is accepted independently.
function ownerRule(css, selector) {
  const normalized = transformSync(css, { loader: 'css', legalComments: 'none', minifyWhitespace: true }).code;
  const rules = normalized.split('}').map(block => {
    const boundary = block.lastIndexOf('{');
    return { selector: block.slice(0, boundary).trim(), declarations: block.slice(boundary + 1) };
  });
  const declarations = rules.filter(rule => rule.selector === selector).map(rule => rule.declarations).join(';');
  return new Map(declarations.split(';').filter(value => value.includes(':')).map(value => {
    const boundary = value.indexOf(':'); return [value.slice(0, boundary).trim(), value.slice(boundary + 1).trim()];
  }));
}
function maxWidthCss(css, width) {
  const normalized = transformSync(css, { loader: 'css', legalComments: 'none', minifyWhitespace: true }).code;
  const blocks = [];
  for (const match of normalized.matchAll(/@media\s*\(max-width:\s*(\d+)px\)\s*\{/g)) {
    if (width > Number(match[1])) continue;
    let end = match.index + match[0].length; const start = end; let depth = 1;
    while (end < normalized.length && depth > 0) { const char = normalized[end++]; if (char === '{') depth++; else if (char === '}') depth--; }
    assert.equal(depth, 0, 'actual CSS media block must be complete'); blocks.push(normalized.slice(start, end - 1));
  }
  return blocks.join('\n');
}
class Element {
  constructor() { this.attrs = new Map(); this.listeners = new Map(); this.textContent = ''; this.style = {}; this.dataset = {}; }
  setAttribute(name, value) { this.attrs.set(name, String(value)); }
  getAttribute(name) { return this.attrs.get(name) ?? null; }
  removeAttribute(name) { this.attrs.delete(name); }
  addEventListener(name, fn) { const list = this.listeners.get(name) || []; list.push(fn); this.listeners.set(name, list); }
  fire(name, detail = {}) { for (const fn of this.listeners.get(name) || []) fn({ type: name, target: this, preventDefault() {}, ...detail }); }
  querySelectorAll() { return []; }
  querySelector() { return null; }
}
function mobileThemeFixture(saved, systemDark) {
  const document = new Element(); const html = new Element(); html.setAttribute('data-lang', 'en'); document.documentElement = html;
  document.readyState = 'loading'; document.cookie = ''; document.body = new Element(); document.createElement = () => new Element();
  const button = source('templates/mobile/base.html').includes('id="m-theme-toggle"') ? new Element() : null;
  document.getElementById = id => id === 'm-theme-toggle' ? button : null;
  const values = new Map(saved ? [['theme', saved]] : []); const localStorage = { getItem: key => values.get(key) || null, setItem: (key, value) => values.set(key, value) };
  const media = new Element(); media.matches = systemDark; media.addListener = fn => media.addEventListener('change', fn);
  const window = new Element(); window.location = new URL('https://bookrank.test/awards?lang=en'); window.localStorage = localStorage;
  window.matchMedia = () => media; window.dispatchEvent = event => window.fire(event.type, event);
  const context = vm.createContext({ document, window, localStorage, URL, URLSearchParams, console, navigator: {},
    CustomEvent: class { constructor(type, init) { this.type = type; this.detail = init.detail; } },
    fetch() { throw new Error('Theme initialization must not fetch'); }, setTimeout() {}, setInterval() { throw new Error('Theme page must not poll'); } });
  vm.runInContext(source('static/mobile/js/mobile.js'), context); document.fire('DOMContentLoaded');
  return { html, button, media, values };
}
for (const [saved, system, expected] of [['light', true, 'light'], ['dark', false, 'dark']]) {
  test(`mobile actual initialization honors existing ${saved} theme over opposite system preference`, () => {
    const f = mobileThemeFixture(saved, system); assert.equal(f.html.getAttribute('data-theme'), expected);
    assert.equal(f.values.get('theme'), saved);
  });
}
test('mobile real early theme script follows system if existing storage is blocked', () => {
  const script = scripts(source('templates/mobile/base.html')).find(s => s.includes("getItem('theme')")); assert.ok(script);
  const html = new Element();
  vm.runInNewContext(script, { document: { documentElement: html }, localStorage: { getItem() { throw new Error('blocked'); } }, window: { matchMedia: () => ({ matches: true }) } });
  assert.equal(html.getAttribute('data-theme'), 'dark');
});
test('mobile actual theme follows system without saved preference then user toggle persists shared key', () => {
  const f = mobileThemeFixture(null, true); assert.equal(f.html.getAttribute('data-theme'), 'dark');
  assert.equal(f.values.has('theme'), false, 'automatic theme must not invent explicit saved preference');
  f.media.matches = false; f.media.fire('change', { matches: false }); assert.equal(f.html.getAttribute('data-theme'), 'light');
  assert.ok(f.button, 'actual mobile base must render a theme control'); f.button.fire('click');
  assert.equal(f.html.getAttribute('data-theme'), 'dark'); assert.equal(f.values.get('theme'), 'dark');
  assert.equal(f.button.getAttribute('aria-pressed'), 'true');
  f.media.matches = false; f.media.fire('change', { matches: false }); assert.equal(f.html.getAttribute('data-theme'), 'dark', 'explicit choice wins after system change');
});

test('real shared base keeps primary menu routes without duplicate reader sidebar or toggle', () => {
  const result = render('base.html');
  assert.equal(result.nodes.some(n => n.attrs.id === 'sidebar' || n.attrs.id === 'sidebar-toggle'), false);
  const menu = result.nodes.find(n => n.tag === 'dialog' && n.attrs.id === 'site-nav-dialog');
  assert.ok(menu, 'existing native primary menu must remain');
  for (const href of ['/', '/rankings', '/awards', '/publishers', '/new-books', '/reports/weekly', '/profile']) {
    assert.ok(result.nodes.some(n => n.tag === 'a' && n.attrs.href === href), href);
  }
  assert.ok(result.nodes.some(n => n.tag === 'a' && n.attrs.href === '/profile' && ancestors(result, n).some(parent => hasClass(parent, 'top-nav'))), 'wide-screen primary navigation must keep visible favorites without opening hidden native menu');
});

const sampleBook = { id: 7, title: 'Original full title', title_en: 'Original full title', title_zh: '完整译名', author: 'Author', isbn13: '9780000000007', isbn10: null, cover_url: '', cover_local_path: '', cover_original_url: '', category: 'Fiction', award_wikidata_id: null, year: 2026, publisher: { id: 1, name: '出版社', name_en: 'Publisher' }, price: 0, publication_date: null, description: 'Unique entire introduction for round3.', description_zh: '第三轮唯一完整简介。', details: '', rank: 1, award_name: 'Award', award_name_en: 'Award', award: { name: 'Award', name_en: 'Award', wikidata_id: null } };
test('mobile awards real filter form is default-collapsed and selected summary/card remain outside', () => {
  const result = render('mobile/awards.html', { data_load_failed: false, total_books: 1, total_pages: 1, page: 1, books: [sampleBook], awards: [{ name: 'Award', name_en: 'Award' }], years: [2026], categories: ['Fiction'], selected_award: 'Award', selected_year: 2026, selected_category: 'Fiction', search_query: 'rain' }, '/awards?lang=zh&view=list&award=Award&year=2026&category=Fiction&search=rain');
  const form = result.nodes.find(n => n.tag === 'form' && hasClass(n, 'm-awards-filter-form')); assert.ok(form);
  const details = ancestors(result, form).find(n => n.tag === 'details'); assert.ok(details, 'real native collapse required'); assert.equal(Object.hasOwn(details.attrs, 'open'), false);
  const info = result.nodes.find(n => hasClass(n, 'm-list-info')); assert.ok(info); assert.equal(ancestors(result, info).includes(details), false);
  for (const text of ['Award', '2026', 'Fiction', 'rain']) assert.ok(info.text.includes(text), text);
  const title = result.nodes.find(n => hasClass(n, 'm-book-title')); assert.ok(title); assert.equal(ancestors(result, title).includes(details), false);
  assert.equal(result.nodes.find(n => n.tag === 'input' && n.attrs.name === 'view').attrs.value, 'list');
  assert.equal(result.nodes.find(n => n.tag === 'input' && n.attrs.name === 'lang').attrs.value, 'zh');
});
test('mobile new-books real filter form is default-collapsed with readable applied state and unchanged CSV', () => {
  const result = render('mobile/new_books.html', { books: [sampleBook], stats: { total_books: 1, active_publishers: 1 }, stats_unavailable: false, data_load_failed: false, publishers_unavailable: false, publisher_sections_unavailable: false, publishers: [sampleBook.publisher], publisher_kind: { 1: 'publisher' }, selected_publisher: 1, selected_days: 30, selected_category: 'Fiction', selected_publication_status: 'pending', search_query: 'rain', categories: [{ name: 'Fiction' }], total: 1, total_pages: 1, page: 1, future_preview_days: 30 }, '/new-books?lang=zh&view=list&publisher=1&days=30&category=Fiction&publication_status=pending&search=rain');
  const form = result.nodes.find(n => n.tag === 'form' && hasClass(n, 'm-filter-bar')); assert.ok(form);
  const details = ancestors(result, form).find(n => n.tag === 'details'); assert.ok(details); assert.equal(Object.hasOwn(details.attrs, 'open'), false);
  const applied = result.nodes.find(n => hasClass(n, 'm-applied-filters')); assert.ok(applied, 'current state must be readable while collapsed');
  assert.equal(ancestors(result, applied).includes(details), false);
  for (const text of ['出版社', '30', 'Fiction', '日期待确认', 'rain']) assert.ok(applied.text.includes(text), text);
  const csv = result.nodes.find(n => n.tag === 'a' && (n.attrs.href || '').startsWith('/api/new-books/export/csv?')); assert.ok(csv);
  const params = new URL(csv.attrs.href, 'https://bookrank.test').searchParams;
  assert.equal(params.get('publisher_id'), '1'); assert.equal(params.get('publication_status'), 'pending'); assert.equal(params.get('search'), 'rain'); assert.equal(params.get('days'), '30'); assert.equal(params.get('category'), 'Fiction');
  const title = result.nodes.find(n => hasClass(n, 'm-book-title')); assert.ok(title); assert.equal(ancestors(result, title).includes(details), false);
});

test('mobile profile real remove button has independent hit target and retains known route plus ISBN', () => {
  const result = render('mobile/profile.html', { favorites: [{ isbn: sampleBook.isbn13, title: 'Title', title_en: 'Original full title', title_zh: '完整译名', author: 'Author', detail_url: '/award-book/7?lang=zh&return_to=%2Fprofile' }], active_tab: 'profile' }, '/profile?lang=zh');
  const button = result.nodes.find(n => n.tag === 'button' && hasClass(n, 'm-fav-remove')); assert.ok(button);
  assert.equal(ancestors(result, button).some(n => n.tag === 'a'), false, 'button cannot be nested in link');
  assert.ok(ancestors(result, button).some(n => hasClass(n, 'm-book-card')), 'remove handler still needs real card ancestor');
  assert.equal(button.attrs['data-isbn'], sampleBook.isbn13);
  assert.ok(result.nodes.some(n => n.tag === 'a' && n.attrs.href === '/award-book/7?lang=zh&return_to=%2Fprofile'));
  assert.ok(result.nodes.some(n => hasClass(n, 'm-book-isbn') && n.text === sampleBook.isbn13));
});

function isContentNode(result, node) {
  return !['script', 'style', 'head'].includes(node.tag) && !ancestors(result, node).some(n => ['script', 'style', 'head'].includes(n.tag));
}
for (const kind of ['nyt', 'award', 'new']) for (const mobile of [false, true]) {
  test(`real ${kind} ${mobile ? 'mobile' : 'desktop'} detail DOM orders title author cover single intro metadata external actions`, () => {
    const name = { nyt: 'book_detail.html', award: 'award_book_detail.html', new: 'new_book_detail.html' }[kind];
    const book = { ...sampleBook, cover_url: 'https://cover.test/book.png', cover: 'https://cover.test/book.png', _original_cover: '', publisher: kind === 'new' ? sampleBook.publisher : 'Publisher', publication_dt: '2026-09-01', publication_year: 2026, publication_date: null, page_count: 123, language: 'en', details_zh: '', weeks_on_list: 2, category_name: 'Fiction', list_name: 'Fiction', buy_links: [{ name: 'Bookstore', url: 'https://store.test/book' }] };
    const result = render((mobile ? 'mobile/' : '') + name, { book, book_index: 0, category: 'fiction', categories: { fiction: '小说' }, category_names_en: { fiction: 'Fiction' }, back_url: '/new-books?lang=zh&view=list', shown_title: book.title_zh, other_title: book.title, safe_title_zh: book.title_zh, safe_title_en: book.title, shown_desc: book.description_zh, buy_links: book.buy_links, related_books: [] });
    const nodes = result.nodes.filter(n => isContentNode(result, n));
    const title = nodes.find(n => n.tag === 'h1' && n.text.includes(book.title_zh)); assert.ok(title);
    const author = nodes.find(n => n.tag === 'p' && n.ownText.trim().startsWith('Author')); assert.ok(author);
    const cover = nodes.find(n => n.tag === 'img' && ((n.attrs.src || '').includes('cover.test') || (n.attrs.src || '').includes('/award-book/7/cover'))); assert.ok(cover);
    const intros = nodes.filter(n => n.ownText.trim() === book.description_zh); assert.equal(intros.length, 1, 'intro must have one real content node, not hero and tab copies');
    const meta = nodes.find(n => n.ownText.includes(book.isbn13)); assert.ok(meta, 'visible ISBN contract retained');
    const external = nodes.find(n => n.tag === 'a' && n.attrs.href === 'https://store.test/book'); assert.ok(external, 'real provided external action retained on both UAs');
    for (const [a, b, label] of [[title, author, 'title before author'], [author, cover, 'author before cover'], [cover, intros[0], 'cover before intro'], [intros[0], meta, 'intro before metadata'], [meta, external, 'metadata before external actions']]) {
      assert.ok(result.nodes.indexOf(a) < result.nodes.indexOf(b), label);
    }
    if (kind !== 'new') assert.equal(nodes.some(n => (n.attrs.id === 'tab-details' || n.attrs['data-tab'] === 'details')), false, 'missing details cannot create empty Details tab');
    if (kind === 'new') assert.equal(nodes.some(n => n.attrs['data-tab'] === 'details'), false, 'NewBook has no details field/tab');
  });
}

function removalFixture(ok) {
  const document = new Element(); const button = new Element(); const card = new Element();
  button.setAttribute('data-isbn', sampleBook.isbn13); button.closest = selector => selector === '.m-fav-remove' ? button : selector === '.m-book-card' ? card : null;
  const cards = [card]; card.remove = () => cards.splice(cards.indexOf(card), 1);
  const empty = new Element(); empty.hidden = true; const count = new Element(); count.textContent = '(1)'; const stat = new Element(); stat.textContent = '已收藏 1 本';
  document.querySelectorAll = selector => { assert.equal(selector, '#m-favorites .m-book-card'); return cards; };
  document.querySelector = selector => ({ '#m-favorites .m-section-count': count, '.m-profile-stat': stat, '#m-favorites-empty': empty })[selector] || null;
  document.getElementById = id => id === 'm-favorites-empty' ? empty : null;
  const calls = []; const notices = []; const ctx = vm.createContext({ document, window: new Element(), pendingIsbns: new Set(), normalizeIsbn: value => value, isZhNow: () => true, favoriteLabels: () => ({ removedToast: 'Removed', errorToast: 'Failed' }), toast: (message,type) => notices.push([message,type]), csrfFetch: async (url, options) => { calls.push([url, options]); return {ok,status:ok?200:500,json:async()=>({success:true})}; } });
  const actual = source('static/mobile/js/mobile.js'); const start = actual.indexOf('    function initFavoriteRemove()'); const end = actual.indexOf('    // ===== 暴露 API =====', start); assert.ok(start >= 0 && end > start, 'real removal source required');
  vm.runInContext(actual.slice(start, end),ctx); ctx.initFavoriteRemove();
  document.fire('click', { target: button, stopPropagation() {} });
  return { cards, empty, count, stat, button, calls, notices };
}
const flushRemoval = async () => { for(let i=0;i<8;i++) await Promise.resolve(); };
test('mobile profile real SSR keeps reusable empty discovery/search state hidden while favorites exist', () => {
  const f=render('mobile/profile.html', { favorites: [{ isbn:sampleBook.isbn13,title:'Title',title_en:'Title',title_zh:'书名',author:'Author',detail_url:'/award-book/7' }],search_history:[] }, '/profile?lang=zh');
  const empty=f.nodes.find(n=>n.attrs.id==='m-favorites-empty'); assert.ok(empty,'last removal cannot reveal markup absent from real SSR'); assert.ok('hidden' in empty.attrs);
  const descendants=f.nodes.filter(n=>n.ancestors.includes(f.nodes.indexOf(empty)));
  assert.ok(descendants.some(n=>n.tag==='form' && n.attrs.action==='/')); assert.ok(descendants.some(n=>n.tag==='input' && n.attrs.name==='search')); assert.ok(descendants.some(n=>n.tag==='a' && n.attrs.href==='/?lang=zh'));
});
test('mobile actual last favorite deletion reveals existing empty state only after success; failure preserves list/count/state', async () => {
  const good=removalFixture(true); assert.equal(good.button.disabled,true); assert.equal(good.empty.hidden,true); await flushRemoval();
  assert.equal(good.cards.length,0); assert.equal(good.count.textContent,'(0)'); assert.equal(good.stat.textContent,'已收藏 0 本'); assert.equal(good.empty.hidden,false,'successful last deletion must reveal discovery/search');
  assert.deepEqual(good.notices,[['Removed','success']]); assert.equal(good.calls.length,1); assert.equal(good.calls[0][1].method,'DELETE');
  const bad=removalFixture(false); await flushRemoval(); assert.equal(bad.cards.length,1); assert.equal(bad.count.textContent,'(1)'); assert.equal(bad.stat.textContent,'已收藏 1 本'); assert.equal(bad.empty.hidden,true); assert.equal(bad.button.disabled,false); assert.deepEqual(bad.notices,[['Failed','error']]);
});

function analyticsThemeFixture() {
  const observers=[]; const charts=[]; const document=new Element(); const html=new Element(); html.setAttribute('data-theme','light'); html.setAttribute('data-lang','en'); html.lang='en'; document.documentElement=html;
  const window=new Element(); window.__APP_LANG__='en'; window.location=new URL('https://bookrank.test/analytics?lang=en');
  class Node extends Element {
    constructor(){super();this.children=[];this._text='';}
    set textContent(value){this._text=String(value);this.children=[];}
    get textContent(){return (this._text||'')+(this.children||[]).map(n=>n.textContent).join('');}
    get firstChild(){return this.children[0]||null;}
    appendChild(n){this.children.push(n);n.parentElement=this;return n;}
    removeChild(n){this.children.splice(this.children.indexOf(n),1);}
  }
  const canvas=new Map(['viewsChart','behaviorChart','dailyChart'].map(id=>{const n=new Node();n.id=id;n.getContext=()=>({canvas:n});return[id,n];}));
  const table=new Node();table.id='top-reports-table';table.tagName='TBODY';canvas.set(table.id,table);
  document.getElementById=id=>canvas.get(id)||null; document.createElement=()=>new Node(); document.createTextNode=text=>({textContent:text});
  let requests=0;
  class Chart {static defaults={}; constructor(_ctx,config){this.data=config.data;this.options=config.options;this.config=config;this.updates=0;charts.push(this);} update(){this.updates++;} destroy(){}}
  class MutationObserver {constructor(callback){observers.push(callback);} observe(){}}
  const roles=()=>html.getAttribute('data-theme')==='dark'?{'--text-primary':'#eeeeee','--text-secondary':'#bbbbbb','--text-muted':'#aaaaaa','--border-color':'#555555','--bg-primary':'#111111','--bg-secondary':'#222222','--bg-tertiary':'#333333'}:{'--text-primary':'#111111','--text-secondary':'#555555','--text-muted':'#666666','--border-color':'#cccccc','--bg-primary':'#ffffff','--bg-secondary':'#f5f5f5','--bg-tertiary':'#eeeeee'};
  const ctx=vm.createContext({document,window,MutationObserver,Chart,URL,Date,Intl,console,getComputedStyle:()=>({getPropertyValue:key=>roles()[key]||''}),fetch:()=>{requests++;throw new Error('theme/language must not request data');}});
  const tpl=process.env.ANALYTICS_LOCALE_SCRIPT_PATH?fs.readFileSync(process.env.ANALYTICS_LOCALE_SCRIPT_PATH,'utf8'):source('templates/analytics_dashboard.html');
  const actual=scripts(tpl).find(s=>s.includes('chartColors'));assert.ok(actual,'actual analytics source required');vm.runInContext(actual,ctx);
  return{ctx,document,window,html,charts,observers,Chart,Node,table,requests:()=>requests};
}
test('analytics actual English loading and error retry labels use current shared locale',()=>{
  const f=analyticsThemeFixture();const status=new f.Node();f.ctx.showLoading(status);assert.equal(status.textContent,'Loading...');f.ctx.showError(status,()=>{});assert.equal(status.textContent,'Failed to load. Please retry.Retry');
});
test('analytics actual charts update neutral axes and legends on dark theme without fetching or recreating',()=>{
  const f=analyticsThemeFixture();vm.runInContext("renderViewsChart([{date:'2026-09-30',view_count:3}]);renderBehaviorChart([{event_type:'view',count:2}]);renderDailyChart([{date:'2026-09-30',count:2}]);",f.ctx);
  assert.equal(f.charts.length,3);assert.ok(f.observers.length,'actual source must observe shared theme changes');
  f.html.setAttribute('data-theme','dark');for(const callback of f.observers)callback([{type:'attributes',attributeName:'data-theme'}]);
  assert.equal(f.charts.length,3,'theme must reuse live chart instances');assert.equal(f.requests(),0);
  for(const chart of f.charts){assert.ok(chart.updates>=1);assert.equal(chart.options.plugins.legend.labels.color,'#eeeeee');for(const axis of Object.values(chart.options.scales||{})){assert.equal(axis.ticks.color,'#eeeeee');assert.equal(axis.grid.color,'#555555');}}
});

test('analytics actual live theme never reads or writes resolved options proxies',()=>{
  const f=analyticsThemeFixture();vm.runInContext("renderViewsChart([{date:'2026-09-30',view_count:3}]);renderBehaviorChart([{event_type:'view',count:2}]);renderDailyChart([{date:'2026-09-30',count:2}]);",f.ctx);
  const before=JSON.stringify(f.charts.map(c=>c.data.datasets.map(d=>d.data)));let reads=0,writes=0;
  for(const c of f.charts)Object.defineProperty(c,'options',{get(){reads++;throw new Error('Resolved Chart option proxy must not be read for copying or reassignment');},set(){writes++;throw new Error('Resolved Chart proxy must not be written back');}});
  f.html.setAttribute('data-theme','dark');f.ctx.applyAnalyticsTheme();f.html.setAttribute('data-theme','light');f.ctx.applyAnalyticsTheme();
  assert.equal(reads,0);assert.equal(writes,0);assert.equal(f.charts.length,3);assert.equal(JSON.stringify(f.charts.map(c=>c.data.datasets.map(d=>d.data))),before);assert.equal(f.requests(),0);
  for(const c of f.charts)assert.equal(c.config.options.plugins.legend.labels.color,'#111111');assert.equal(f.charts[2].config.options.scales.x.type,'linear');
});

test('analytics real language event refreshes canvas accessible names and an existing retry panel without requesting data',()=>{
  const f=analyticsThemeFixture(); const status=new f.Node();
  f.document.querySelectorAll=selector=>selector==='.panel-status'?[status]:[];
  f.ctx.showError(status,()=>{});
  f.window.__APP_LANG__='zh'; f.html.setAttribute('data-lang','zh'); f.window.fire('languagechange',{detail:{language:'zh'}});
  assert.equal(status.textContent,'加载失败，请重试重试');
  assert.equal(f.document.getElementById('viewsChart').getAttribute('aria-label'),'周报累计阅读量');
  assert.equal(f.document.getElementById('behaviorChart').getAttribute('aria-label'),'用户行为事件分布');
  assert.equal(f.document.getElementById('dailyChart').getAttribute('aria-label'),'每日用户行为事件数');
  f.window.__APP_LANG__='en'; f.html.setAttribute('data-lang','en'); f.window.fire('languagechange',{detail:{language:'en'}});
  assert.equal(status.textContent,'Failed to load. Please retry.Retry');
  assert.equal(f.document.getElementById('viewsChart').getAttribute('aria-label'),'Cumulative weekly report views');
  assert.equal(f.document.getElementById('behaviorChart').getAttribute('aria-label'),'User behavior event distribution');
  assert.equal(f.document.getElementById('dailyChart').getAttribute('aria-label'),'Daily user behavior events');
  assert.equal(f.requests(),0);
});

test('analytics actual table view and empty text switch while literal title/date/count and link stay intact',()=>{
  const f=analyticsThemeFixture();f.document.querySelectorAll=s=>{
    const all=[];function walk(n){all.push(n);for(const child of n.children||[])walk(child);}walk(f.table);
    return s==='[data-analytics-text]'?all.filter(n=>n.dataset&&n.dataset.analyticsText):[];
  };
  f.ctx.renderTopReports([{date:'2026-09-30',title:'<script >literal</script >',view_count:7}]);
  const row=f.table.children[0];const link=row.children[3].children[0];const href=link.href;
  f.window.__APP_LANG__='zh';f.window.fire('languagechange',{detail:{language:'zh'}});
  assert.equal(link.textContent,'查看');assert.equal(link.href,href);assert.deepEqual(row.children.slice(0,3).map(n=>n.textContent),['2026-09-30','<script >literal</script >','7']);
  f.ctx.renderTopReports([]);const empty=f.table.children[0].children[0];assert.equal(empty.textContent,'暂无数据');
  f.window.__APP_LANG__='en';f.window.fire('languagechange',{detail:{language:'en'}});assert.equal(empty.textContent,'No data available');assert.equal(f.requests(),0);
});

test('publisher ranking actual table keeps all labeled metric values for narrow-screen cards',()=>{
  const entry={name:'Full Publisher',book_count:7,category_count:3,best_rank:2,total_weeks:19,books:[{title:'Full Original Work',title_zh:'译名'}]};
  const f=render('rankings.html',{tab:'publishers',category_count:5,cross_entries:[],longevity_entries:[],overlooked_entries:[],publisher_entries:[entry],award_years:[2026],category_names_en:{},update_time:'2026-09-30'},'/rankings?tab=publishers&lang=en','en');
  const table=f.nodes.find(n=>hasClass(n,'publisher-table'));assert.ok(table);
  const row=f.nodes.find(n=>n.tag==='tr' && ancestors(f,n).some(p=>p.tag==='tbody'));
  const cells=f.nodes.filter(n=>n.ancestors.includes(f.nodes.indexOf(row)) && (n.tag==='td'||n.tag==='th'));
  assert.equal(cells.length,7);
  for(const cell of cells)assert.ok(cell.attrs['data-label'],'each responsive card value needs a real localized label');
  assert.deepEqual(cells.map(n=>n.text.trim()),['1','Full Publisher','7','3','#2','19','Full Original Work']);
});

for(const name of ['analytics_dashboard.html','cache_management.html']) test(`${name} actual static text switches through existing translation mechanism`,()=>{
  const f=render(name);const owner=f.nodes.find(n=>hasClass(n,name.startsWith('analytics')?'dashboard-container':'cache-management-page'));assert.ok(owner);
  const nodes=f.nodes.filter(n=>n.ancestors.includes(f.nodes.indexOf(owner)));
  const heading=nodes.find(n=>n.tag==='h1');assert.ok(heading);
  const hook=nodes.find(n=>n.ancestors.includes(f.nodes.indexOf(heading)) && n.attrs['data-en'] && n.attrs['data-zh']);assert.ok(hook,'real heading must have a language-switch hook');
  const hooked=nodes.filter(n=>n.attrs['data-en'] && n.attrs['data-zh']);assert.ok(hooked.length>=12,'all page chrome needs real hooks');
  const elements=hooked.map(n=>({attrs:n.attrs,childNodes:[{nodeType:3,textContent:n.ownText.trim()}],getAttribute(k){return this.attrs[k]??null;},querySelector(){return null;}}));
  const document={querySelectorAll:s=>s==='[data-zh][data-en]'?elements:[],querySelector:()=>null};
  const text=source('static/js/translations.js');const start=text.indexOf('function setVisibleText(');const end=text.indexOf('function setGlobalLanguage(',start);assert.ok(start>=0&&end>start);
  const ctx=vm.createContext({document,Node:{TEXT_NODE:3}});vm.runInContext(text.slice(start,end),ctx);
  ctx.applyPageTranslation('en');for(const el of elements)assert.equal(el.childNodes[0].textContent,el.attrs['data-en']);
  ctx.applyPageTranslation('zh');for(const el of elements)assert.equal(el.childNodes[0].textContent,el.attrs['data-zh']);
});

test('weekly actual five charts keep numbers while theme and language change live accessible canvas names',()=>{
  const actual=source('templates/weekly_report_detail.html');const start=actual.indexOf('        const chartColors =');const end=actual.lastIndexOf('    }\n});');assert.ok(start>=0&&end>start);
  const code="import json,sys;from jinja2 import Environment;sys.stdin.reconfigure(encoding='utf8');sys.stdout.reconfigure(encoding='utf8');s=json.load(sys.stdin);e=Environment();e.globals['_']=lambda v:v;print(e.from_string(s).render())";
  const rendered=spawnSync(process.env.PYTHON||'python',['-c',code],{input:JSON.stringify(actual.slice(start,end)),encoding:'utf8'});assert.equal(rendered.status,0,rendered.stderr);
  const document=new Element();const html=new Element();html.setAttribute('data-theme','light');html.setAttribute('data-lang','en');document.documentElement=html;
  const ids=['top-changes-chart','category-chart','trend-chart','week-comparison-chart','stability-chart'];const canvases=new Map(ids.map(id=>{const n=new Element();n.getContext=()=>id;return[id,n];}));document.getElementById=id=>canvases.get(id);
  const window=new Element();window.__APP_LANG__='en';const callbacks=[];const charts=[];
  const getComputedStyle=()=>({getPropertyValue:k=>({'--text-primary':html.getAttribute('data-theme')==='dark'?'#eeeeee':'#171717','--text-secondary':'#aaaaaa','--text-muted':'#bbbbbb','--border-color':'#555555','--bg-secondary':'#222222'})[k]||''});window.getComputedStyle=getComputedStyle;
  class Chart{constructor(id,c){this.id=id;this.data=c.data;this.options=c.options;this.config=c;this.updates=0;charts.push(this);}update(){this.updates++;}}
  class MutationObserver{constructor(fn){callbacks.push(fn);}observe(){}}
  const reportContent={top_changes:[{title:'Gain',rank:3,rank_change:2},{title:'Loss',rank:5,rank_change:-3},{title:'New',rank:2,rank_change:0,is_new:true},{title:'Unknown',rank:4,rank_change:null}],category_chart:{available:true,labels:['A','B'],counts:[7,3]}};
  const ctx=vm.createContext({document,window,Chart,MutationObserver,getComputedStyle,reportContent,console,fetch(){throw new Error('theme/language must not fetch');}});vm.runInContext(rendered.stdout,ctx);
  assert.equal(charts.length,5);const numbers=JSON.stringify(charts.map(c=>c.data.datasets.map(d=>d.data)));assert.ok(callbacks.length,'real charts need shared theme subscription');
  html.setAttribute('data-theme','dark');for(const fn of callbacks)fn([{attributeName:'data-theme'}]);
  assert.equal(charts.length,5);assert.equal(JSON.stringify(charts.map(c=>c.data.datasets.map(d=>d.data))),numbers);
  for(const c of charts){assert.ok(c.updates>0);assert.equal(c.options.plugins.legend.labels.color,'#eeeeee');for(const axis of Object.values(c.options.scales||{}))assert.equal(axis.ticks.color,'#aaaaaa');}
  assert.equal(charts[4].options.scales.r.pointLabels.color,'#aaaaaa');
  window.__APP_LANG__='zh';window.fire('languagechange',{detail:{language:'zh'}});assert.equal(canvases.get(ids[0]).getAttribute('aria-label'),'本周排名变化图');
  window.__APP_LANG__='en';window.fire('languagechange',{detail:{language:'en'}});assert.equal(canvases.get(ids[0]).getAttribute('aria-label'),'Weekly rank changes');assert.equal(canvases.get(ids[4]).getAttribute('aria-label'),'Rank change magnitude');
});

for(const mobile of [false,true]) test(`home ${mobile?'mobile':'desktop'} real Chinese card visibly retains complete original title; English has one title`,()=>{
  const book={...sampleBook,title:'DEAD END GIRL: The full original title',title_zh:'死路一条',cover:'https://cover.test/image.png',is_new:false,is_returning:false,weeks_on_list:2,publisher:'Publisher'};
  const input={books:[book],categories:{fiction:'小说'},current_category:'fiction',category_names_en:{fiction:'Fiction'},total:1,total_books:1,search_query:'',is_cached:false,monthly_categories:[],search_unavailable_count:0};
  const name=(mobile?'mobile/':'')+'index.html';const f=render(name,input,'/?lang=zh');
  const original=f.nodes.filter(n=>hasClass(n,mobile?'m-book-original-title':'card-original-title'));
  assert.equal(original.length,1,'translated card must have a real secondary original text node');assert.equal(original[0].text,book.title);
  const en=render(name,input,'/?lang=en','en');assert.equal(en.nodes.some(n=>hasClass(n,mobile?'m-book-original-title':'card-original-title')),false);
  assert.ok(en.nodes.some(n=>n.tag==='h3' && n.text.trim()===book.title));
});

test('mobile weekly actual month options and headings show readable English month names',()=>{
  const r={title:'Report',week_start:'2026-09-21',week_end:'2026-09-27',report_date:'2026-09-27',content_data:{title_display:'Report',summary:'Summary'}};
  const f=render('mobile/weekly_reports.html',{reports:[r],latest_report:r,report_sections:[{year:2026,month:9,reports:[r]}],is_generating:false},'/reports/weekly?lang=en','en');
  assert.equal(f.nodes.find(n=>n.tag==='option'&&n.attrs.value==='2026-09').text,'September 2026');
  assert.equal(f.nodes.find(n=>hasClass(n,'m-report-group-title')).text,'September 2026');
});

function cacheLocaleFixture(responseStatus) {
  class N extends Element{constructor(){super();this.children=[];this._text='';this.className='';this.disabled=false;this.classList={add(){},remove(){}};}set textContent(v){this._text=String(v);this.children=[];}get textContent(){return (this._text||'')+this.children.map(n=>n.textContent).join('');}appendChild(n){this.children.push(n);n.parentElement=this;return n;}remove(){if(this.parentElement)this.parentElement.children.splice(this.parentElement.children.indexOf(this),1);}querySelector(s){return this.children.find(n=>(n.className||'').split(/\s+/).includes(s.slice(1)))||null;}}
  const document=new Element();document.documentElement={lang:'zh'};const nodes=[];const ids=new Map();
  for(const id of ['translation-list','translation-stats-container','api-list','api-stats-container','btn-clear-translation','btn-clear-all-translation','btn-clear-api','btn-clear-expired']){const n=new N();n.id=id;n.disabled=id.startsWith('btn-clear');nodes.push(n);ids.set(id,n);}
  document.getElementById=id=>ids.get(id)||null;document.createElement=()=>{const n=new N();nodes.push(n);return n;};
  document.querySelectorAll=s=>s==='.cache-status-msg, .cache-retry-btn, .loading-state p, .empty-state p'?nodes.filter(n=>['cache-status-msg','cache-retry-btn'].some(c=>n.className.split(/\s+/).includes(c))):[];
  const window=new Element();let calls=0;const ctx=vm.createContext({document,window,console:{error(){}},fetch:async()=>{calls++;return{ok:false,status:responseStatus,json:async()=>({success:false})};}});
  const html=process.env.CACHE_LOCALE_SCRIPT_PATH?fs.readFileSync(process.env.CACHE_LOCALE_SCRIPT_PATH,'utf8'):source('templates/cache_management.html');const actual=scripts(html).find(s=>s.includes('function loadTranslationRecords'));assert.ok(actual);vm.runInContext(actual,ctx);
  return {document,window,ctx,ids,requests:()=>calls};
}
test('cache actual denied message switches locale without a request or weakening the authorization latch',async()=>{
  const {document,window,ctx,ids,requests}=cacheLocaleFixture(403);
  await ctx.loadTranslationRecords();const status=ids.get('translation-list').querySelector('.cache-status-msg');assert.ok(status);assert.equal(status.textContent,'权限不足，无法查看或操作翻译缓存。');assert.equal(ctx.groupStateStatus('translation'),'denied');
  document.documentElement.lang='en';window.fire('languagechange',{detail:{language:'en'}});assert.equal(status.textContent,'Insufficient permissions to view or manage translation cache.');assert.equal(requests(),1);assert.equal(ctx.groupStateStatus('translation'),'denied');
  for(const [id,n] of ids)if(id.startsWith('btn-clear'))assert.equal(n.disabled,true);
});

test('cache real concurrent 500 panels keep their own bilingual identity without stale error suffixes',async()=>{
  const {document,window,ctx,ids,requests}=cacheLocaleFixture(500);
  await Promise.all([ctx.loadTranslationStats(),ctx.loadTranslationRecords(),ctx.loadAPIStats(),ctx.loadAPIRecords()]);assert.equal(requests(),4);
  document.documentElement.lang='en';window.fire('languagechange',{detail:{language:'en'}});
  for(const [id,text] of [['translation-stats-container','Failed to load translation cache stats. Please retry.'],['api-stats-container','Failed to load API cache stats. Please retry.'],['translation-list','Failed to load translation cache records. Please retry.'],['api-list','Failed to load API cache records. Please retry.']]){
    const node=ids.get(id).querySelector('.cache-status-msg');assert.ok(node);assert.equal(node.textContent,text);const retry=ids.get(id).querySelector('.cache-retry-btn');assert.ok(retry);assert.equal(retry.textContent,'Retry');
  }
  document.documentElement.lang='zh';window.fire('languagechange',{detail:{language:'zh'}});assert.equal(ids.get('translation-stats-container').querySelector('.cache-status-msg').textContent,'加载翻译缓存统计失败，请重试');assert.equal(ids.get('api-stats-container').querySelector('.cache-status-msg').textContent,'加载API缓存统计失败，请重试');assert.equal(requests(),4);
  for(const [id,n] of ids)if(id.startsWith('btn-clear'))assert.equal(n.disabled,true);
});

test('actual cache clear-all confirmation uses English and declining sends no mutation',async()=>{
  const {document,ctx,requests}=cacheLocaleFixture(500);document.documentElement.lang='en';let seen='';ctx.confirm=message=>{seen=message;return false;};ctx.setCacheAuthorized('translation',true);
  await ctx.clearAllTranslationCache();assert.equal(seen,'Clear all translation cache? This cannot be undone.');assert.equal(requests(),0);
});

for(const name of ['error.html','mobile/error.html']) test(`${name} real missing-book explanation differs from heading and keeps source return`,()=>{
  const f=render(name,{message:'书籍不存在',heading:'书籍不存在',back_url:'/new-books?publication_status=pending&view=list&lang=zh'});
  const h=f.nodes.find(n=>n.tag==='h1');const p=f.nodes.find(n=>hasClass(n,name.startsWith('mobile/')?'m-error-message':'error-message'));assert.ok(h&&p);
  assert.notEqual(p.text,h.text);assert.ok(p.text.includes('返回列表'));assert.ok(f.nodes.some(n=>n.tag==='a'&&n.attrs.href==='/new-books?publication_status=pending&view=list&lang=zh'));
});

test('publisher ranking real narrow-card labels switch through its actual language event',()=>{
  const entry={name:'Publisher',book_count:7,category_count:3,best_rank:2,total_weeks:19,books:[{title:'Original work'}]};
  const f=render('rankings.html',{tab:'publishers',category_count:5,cross_entries:[],longevity_entries:[],overlooked_entries:[],publisher_entries:[entry],award_years:[2026],category_names_en:{},update_time:'2026-09-30'},'/rankings?tab=publishers&lang=en','en');
  const values=f.nodes.filter(n=>n.attrs['data-label']);assert.equal(values.length,7);
  const nodes=values.map(n=>{const el=new Element();for(const [k,v] of Object.entries(n.attrs))el.setAttribute(k,v);el.textContent=n.text;return el;});
  const document={documentElement:{lang:'en'},body:{lang:''},querySelectorAll:s=>s==='[data-label-zh][data-label-en]'?nodes:[]};const window=new Element();window.__APP_LANG__='en';
  const actual=scripts(f.html).find(s=>s.includes('data-label-zh'));assert.ok(actual,'real label script must exist');vm.runInNewContext(actual,{document,window});
  assert.deepEqual(nodes.map(n=>n.getAttribute('data-label')),['Rank','Publisher','Books on list','Categories covered','Best rank','Total weeks on list','Representative books']);
  window.__APP_LANG__='zh';window.fire('languagechange',{detail:{language:'zh'}});assert.deepEqual(nodes.map(n=>n.getAttribute('data-label')),['排名','厂牌','上榜本数','覆盖分类','最高名次','合计在榜周','代表作']);assert.deepEqual(nodes.map(n=>n.textContent),values.map(n=>n.text));
});

test('home actual renderer displays words and symbols for both directions and known stable/new states',()=>{
  const s=source('static/js/index.js');const start=s.indexOf('function renderRankChange(');const end=s.indexOf('function renderCoverWeeks(',start);assert.ok(start>=0&&end>start);
  const ctx=vm.createContext({esc:v=>String(v),t:(key,lang,{n}={})=>`${key} ${n||''}`});vm.runInContext(s.slice(start,end),ctx);
  for(const lang of ['zh','en']){
    const up=ctx.renderRankChange({previous_rank:5},3,lang,'rank-change');const down=ctx.renderRankChange({previous_rank:2},5,lang,'rank-change');
    assert.ok(up.includes(lang==='zh'?'↑ 上升 2':'↑ Up 2'));assert.ok(down.includes(lang==='zh'?'↓ 下降 3':'↓ Down 3'));
    assert.ok(ctx.renderRankChange({previous_rank:3},3,lang,'rank-change').includes(lang==='zh'?'— 持平':'— Unchanged'));
    assert.ok(ctx.renderRankChange({is_new:true},3,lang,'rank-change').includes(lang==='zh'?'+ 新':'+ NEW'));assert.equal(ctx.renderRankChange({is_new:false,is_returning:false},3,lang,'rank-change'),'');
  }
});

test('actual desktop toast close name follows current valid URL language',()=>{
  const s=process.env.BASE_TOAST_SOURCE_PATH?fs.readFileSync(process.env.BASE_TOAST_SOURCE_PATH,'utf8'):source('static/js/base.js');
  const start=s.indexOf('    function showToast(');const end=s.indexOf('    /**',start);const ls=s.indexOf('    function getCurrentLang()');const le=s.indexOf('    /**',ls);assert.ok(start>=0&&end>start&&ls>=0&&le>ls);
  for(const lang of ['en','zh']){
    const toasts=[];const toastContainer={appendChild:n=>toasts.push(n)};const document={createElement(){const n=new Element();n.classList={add(){}};n.querySelector=()=>null;return n;}};
    const window={location:new URL('https://bookrank.test/cache-management?lang='+lang)};const ctx=vm.createContext({toastContainer,document,window,iconMap:{info:'icon-info'},esc:v=>String(v),localStorage:{getItem:()=>lang==='en'?'zh':'en'},navigator:{language:'zh'},URLSearchParams,requestAnimationFrame:fn=>fn(),setTimeout:()=>1});
    vm.runInContext(s.slice(ls,le)+s.slice(start,end),ctx);ctx.showToast('Saved');assert.equal(toasts.length,1);assert.ok(toasts[0].innerHTML.includes('aria-label="'+(lang==='en'?'Close notification':'关闭提示')+'"'));assert.equal(toasts[0].getAttribute('role'),'alert');
  }
});

test('mobile home real badges preserve new/returning priority and never label unknown as unchanged',()=>{
  const cases=[{previous_rank:5,rank:3,is_new:false,is_returning:false},{previous_rank:2,rank:5,is_new:false,is_returning:false},{previous_rank:3,rank:3,is_new:false,is_returning:false},{previous_rank:0,rank:2,is_new:true,is_returning:false},{previous_rank:0,rank:4,is_new:false,is_returning:true},{previous_rank:0,rank:8,is_new:false,is_returning:false}];
  const books=cases.map((b,i)=>({...sampleBook,...b,id:i+1,title:'Book '+i,title_zh:'图书'+i,publisher:'Publisher'}));
  const f=render('mobile/index.html',{books,categories:{fiction:'小说'},current_category:'fiction',category_names_en:{fiction:'Fiction'},search_query:'',is_cached:false},'/?lang=zh');
  const badges=f.nodes.filter(n=>hasClass(n,'m-book-rank-change'));assert.deepEqual(badges.map(n=>n.text.trim()),['↑ 上升 2','↓ 下降 3','— 持平','+ 新','↩ 重返']);
});

test('directory real cards retain website links and change each actual label without filtering or fetching',()=>{
  const pub={name:'测试出版社',name_en:'Test Publisher',url:'https://publisher.test/catalog',description:'中文定位',description_en:'English focus'};
  const f=render('publishers.html',{total_publishers:1,publishers_data:[{category:'出版社',category_en:'Publishers',publishers:[pub]}],new_books_publisher_ids:{'Test Publisher':1},publisher_sections:[]},'/publishers?lang=zh');
  const row=f.nodes.find(n=>n.tag==='tr'&&n.attrs['data-name-en']==='Test Publisher');assert.ok(row);const cells=f.nodes.filter(n=>n.tag==='td'&&n.ancestors.includes(f.nodes.indexOf(row)));assert.equal(cells.length,4);
  const nodes=cells.map(n=>{const el=new Element();for(const[k,v]of Object.entries(n.attrs))el.setAttribute(k,v);return el;});const elRow={querySelectorAll:s=>s==='td'?nodes:[]};const window=new Element();window.__APP_LANG__='zh';
  const document={readyState:'complete',documentElement:{lang:'zh-CN'},querySelectorAll:s=>s==='.publishers-page .publishers-table tbody tr'?[elRow]:[]};const actual=scripts(f.html).find(s=>s.includes('function applyLabels'));assert.ok(actual);vm.runInNewContext(actual,{window,document,fetch(){throw new Error('label changes must not fetch');}});
  assert.deepEqual(nodes.map(n=>n.getAttribute('data-label')),['中文名称','英文名称','核心定位','新书速递']);window.fire('languagechange',{detail:{language:'en'}});assert.deepEqual(nodes.map(n=>n.getAttribute('data-label')),['Chinese Name','English Name','Core focus','New books']);
  assert.ok(f.nodes.some(n=>n.tag==='a'&&n.attrs.href===pub.url&&n.text.includes(pub.name)));assert.ok(f.nodes.some(n=>n.tag==='a'&&n.attrs.href==='/new-books?publisher=1'));
});

test('mobile weekly real new and recommended book titles use English outside the changes loop',()=>{
  const book={title:'Full original title',title_zh:'完整译名',author:'Author',cover:'',cover_url:'',rank:3,weeks_on_list:8,rank_change:2,is_new:false};
  const input={report:{title:'Report',week_start:'2026-09-21',week_end:'2026-09-27',report_date:'2026-09-27',created_at:'2026-09-27T12:00:00'},content:{top_changes:[],new_books:[book],featured_books:[book]},safe_summary:''};
  const en=render('mobile/weekly_report_detail.html',input,'/reports/weekly/2026-09-27?lang=en','en');
  assert.equal(en.nodes.find(n=>hasClass(n,'m-book-title')).text,book.title);assert.equal(en.nodes.find(n=>hasClass(n,'m-report-rec-title')).text,book.title);assert.equal(en.nodes.some(n=>hasClass(n,'m-report-original-title')),false);
  const zh=render('mobile/weekly_report_detail.html',input,'/reports/weekly/2026-09-27?lang=zh');assert.deepEqual(zh.nodes.filter(n=>hasClass(n,'m-report-original-title')).map(n=>n.text),[book.title,book.title]);assert.equal(zh.nodes.find(n=>hasClass(n,'m-book-title')).text,book.title_zh);
});

test('weekly actual theme mutates raw configuration without enumerating or assigning resolved Chart option proxies',()=>{
  const s=source('templates/weekly_report_detail.html');const start=s.indexOf('function readThemeRole(');const end=s.indexOf('function refreshAllWeeklyCharts()',start);assert.ok(start>=0&&end>start);
  const raw={plugins:{tooltip:{callbacks:{label:()=>'+2'}},legend:{display:true}},scales:{x:{reverse:true},y:{beginAtZero:true,ticks:{callback:n=>n}}}};
  const cache=new WeakMap();let writes=0;function resolved(target){if(!target||typeof target!=='object')return target;if(cache.has(target))return cache.get(target);const proxy=new Proxy(target,{get:(obj,key)=>resolved(obj[key]),ownKeys(){throw new Error('Chart resolved descriptors must not be enumerated');}});cache.set(target,proxy);return proxy;}
  const chart={config:{type:'bar',options:raw},data:{datasets:[{data:[2,-3,null,0],backgroundColor:['#123','#456','#789','#abc']}]},updates:0,update(){this.updates++;}};Object.defineProperty(chart,'options',{get:()=>resolved(raw),set(){writes++;throw new Error('Resolved proxy must not be assigned back to raw config');}});
  const document={documentElement:{}};const window={getComputedStyle:()=>({getPropertyValue:k=>({'--text-primary':'#eee','--text-secondary':'#aaa','--text-muted':'#bbb','--border-color':'#555','--bg-secondary':'#222'})[k]||''})};const ctx=vm.createContext({document,window});vm.runInContext(s.slice(start,end),ctx);
  const before=JSON.stringify(chart.data.datasets[0].data);const callback=raw.plugins.tooltip.callbacks.label;const tick=raw.scales.y.ticks.callback;ctx.applyWeeklyChartTheme(chart);ctx.applyWeeklyChartTheme(chart);
  assert.equal(writes,0);assert.equal(chart.updates,2);assert.equal(JSON.stringify(chart.data.datasets[0].data),before);assert.equal(raw.plugins.tooltip.callbacks.label,callback);assert.equal(raw.scales.y.ticks.callback,tick);assert.equal(raw.scales.x.reverse,true);assert.equal(raw.scales.y.beginAtZero,true);assert.equal(raw.plugins.legend.labels.color,'#eee');assert.equal(raw.scales.y.ticks.color,'#aaa');
});

test('weekly list real SSR action owner prevents the 38px override at 1280 and 390', () => {
  const reports = Array.from({ length: 5 }, (_, i) => ({ title: `Weekly report ${i + 1}`, report_date: `2026-09-${27 - i}`, week_start: '2026-09-21', week_end: '2026-09-27', content_data: { summary: '' } }));
  const result = render('weekly_reports.html', { reports, report_sections: [{ year: 2026, month: 9, reports }], latest_report: reports[0], is_generating: false }, '/reports/weekly?lang=en', 'en');
  const body = result.nodes.find(node => node.tag === 'body'); assert.ok(hasClass(body, 'weekly-page'));
  const actions = result.nodes.filter(node => ['a', 'button'].includes(node.tag) && hasClass(node, 'btn') && ancestors(result, node).some(parent => hasClass(parent, 'news-actions')));
  assert.equal(actions.length, 10); assert.equal(actions.filter(node => node.tag === 'a').length, 5); assert.equal(actions.filter(node => node.attrs['data-report-date']).length, 5);
  for (const action of actions.filter(node => node.tag === 'a')) assert.ok(action.attrs.href.startsWith('/reports/weekly/'));
  assert.ok(source('static/css/app.entry.css').includes("@import 'weekly.css';"));
  const selector = '.weekly-page .news-actions .btn';
  let minimum = ownerRule(source('static/css/weekly.css'), selector).get('min-height');
  for (const style of result.nodes.filter(node => node.tag === 'style')) minimum = ownerRule(style.text, selector).get('min-height') || minimum;
  for (const width of [1280, 390]) assert.ok(Number.parseFloat(minimum) >= 44, `${width}px: actual unconditional owner min-height is ${minimum}`);
});

test('publisher real SSR search keeps input and 44px clear in one shrinkable row', () => {
  const result = render('publishers.html', { total_publishers: 0, publishers_data: [], new_books_publisher_ids: {}, publisher_sections: [] }, '/publishers?lang=en', 'en');
  const wrapper = result.nodes.find(node => hasClass(node, 'publishers-search')); assert.ok(wrapper);
  const children = result.nodes.filter(node => node.ancestors.at(-1) === result.nodes.indexOf(wrapper));
  assert.ok(children.some(node => node.tag === 'svg' && hasClass(node, 'icon'))); assert.ok(children.some(node => node.tag === 'input' && node.attrs.id === 'search-input')); assert.ok(children.some(node => node.tag === 'button' && node.attrs.id === 'clear-search-btn'));
  const css = source('static/css/publishers.css'); const row = ownerRule(css, '.publishers-search'); const input = ownerRule(css, '.publishers-search input'); const button = ownerRule(css, '.publishers-search #clear-search-btn');
  assert.equal(row.get('display'), 'flex', 'a block with width:100% input places clear on a second line'); assert.ok(!row.has('flex-wrap') || row.get('flex-wrap') === 'nowrap'); assert.equal(row.get('align-items'), 'center');
  assert.equal(input.get('min-width'), '0', 'input must shrink at 320px'); assert.ok(input.get('flex'), 'input must share remaining row width');
  assert.ok(Number.parseFloat(button.get('min-height')) >= 44); assert.ok(Number.parseFloat(button.get('min-width')) >= 44); assert.equal(button.get('flex-shrink'), '0');
  const icon = ownerRule(css, '.publishers-search .icon'); assert.equal(icon.get('top'), '50%'); assert.equal(icon.get('transform'), 'translateY(-50%)');
});

test('real NYT metadata labels use shared light and dark text roles', () => {
  const book = { ...sampleBook, cover: '', _original_cover: '', publisher: 'Publisher', details_zh: '', category_name: 'Fiction', weeks_on_list: 2, page_count: 123, language: 'en', publication_dt: '2026-09-01' };
  const result = render('book_detail.html', { book, book_index: 0, category: 'fiction', categories: { fiction: '小说' }, category_names_en: { fiction: 'Fiction' }, back_url: '/' }, '/book/0?lang=zh');
  const labels = result.nodes.filter(node => node.tag === 'dt' && ancestors(result, node).some(parent => hasClass(parent, 'detail-meta-row'))); assert.ok(labels.length >= 7);
  const css = result.nodes.filter(node => node.tag === 'style').map(node => node.text).join('\n');
  assert.ok(['var(--text-secondary)', 'var(--text-muted)'].includes(ownerRule(css, '.detail-meta-row dt').get('color')), 'low-contrast local rgba(0,0,0,.48) must not color metadata labels');
});

test('real new-books source-kind labels use shared text roles for all three actual branches', () => {
  const sections = [1, 2, 3].map(id => ({ publisher: { id, name: `来源${id}`, name_en: `Source ${id}` }, books: [] }));
  const result = render('new_books.html', { books: [], stats: { total_books: 0, active_publishers: 3, active_providers: 0 }, stats_unavailable: false, data_load_failed: false, publishers_unavailable: false, publisher_sections_unavailable: false, publishers: sections.map(section => section.publisher), publisher_labels: {}, category_alias_labels: {}, publisher_kind: { 1: 'publisher', 2: 'provider' }, publisher_sections: sections, publisher_book_counts: {}, publisher_counts_unavailable: false, selected_publisher: null, selected_days: 30, selected_category: '', selected_publication_status: 'all', search_query: '', categories: [], total: 0, total_pages: 0, page: 1, future_preview_days: 30 }, '/new-books?lang=zh');
  const labels = result.nodes.filter(node => hasClass(node, 'browse-section-kind')); assert.equal(labels.length, 3); assert.deepEqual(labels.map(node => node.text.trim()), ['出版社', '数据提供方', '未分类来源']);
  for (const label of labels) {
    const css = transformSync(`.label {${label.attrs.style}}`, { loader: 'css' }).code;
    assert.ok(['var(--text-secondary)', 'var(--text-muted)'].includes(ownerRule(css, '.label').get('color')), `actual source-kind inline color: ${label.attrs.style}`);
  }
});

test('real weekly overview paragraphs override narrow shared white text with a theme role', () => {
  const result = render('weekly_report_detail.html', { report: { title: 'Report', week_start: '2026-09-21', week_end: '2026-09-27', report_date: '2026-09-27', created_at: '2026-09-27T12:00:00' }, content: { top_changes: [], new_books: [], featured_books: [] }, safe_summary: '<p>Actual overview paragraph.</p>' }, '/reports/weekly/2026-09-27?lang=zh');
  assert.ok(hasClass(result.nodes.find(node => node.tag === 'body'), 'weekly-detail-page'));
  const paragraph = result.nodes.find(node => node.tag === 'p' && node.text === 'Actual overview paragraph.'); assert.ok(paragraph); assert.ok(ancestors(result, paragraph).some(node => hasClass(node, 'report-summary-content'))); assert.ok(ancestors(result, paragraph).some(node => hasClass(node, 'tab-panel')));
  const css = result.nodes.filter(node => node.tag === 'style').map(node => node.text).join('\n');
  assert.ok(['var(--text-secondary)', 'var(--text-muted)'].includes(ownerRule(css, '.weekly-detail-page .tab-panel p').get('color')), 'specific weekly paragraph rule must override narrow .tab-panel p white text in both themes');
});

test('real home export button and scope note occupy separate responsive rows without shrinking text', () => {
  const result = render('index.html', { books: [{ ...sampleBook, publisher: 'Publisher', cover: '', _original_cover: '', previous_rank: 0, is_new: true }], categories: { fiction: '小说' }, current_category: 'fiction', category_names_en: { fiction: 'Fiction' }, monthly_categories: [], search_query: '', search_unavailable_count: 0, is_cached: false, data_load_failed: false, search_partial: false }, '/?lang=zh');
  const button = result.nodes.find(node => node.attrs.id === 'btn-export-all'); assert.ok(button); const note = result.nodes.find(node => hasClass(node, 'export-scope-note')); assert.ok(note);
  const parent = ancestors(result, button).find(node => hasClass(node, 'export-buttons')); assert.ok(parent); assert.ok(ancestors(result, note).includes(parent)); assert.ok(button.text.includes('全部 NYT 分类')); assert.ok(note.text.includes('当前搜索与分类筛选'));
  assert.ok(ancestors(result, button).some(node => hasClass(node, 'home-toolbar')));
  const css = source('static/css/index.css');
  for (const width of [320, 390, 768]) {
    const rules = maxWidthCss(css, width); const row = ownerRule(rules, 'body.charts-page .home-toolbar .export-buttons'); const btn = ownerRule(rules, 'body.charts-page .home-toolbar .export-buttons #btn-export-all'); const caption = ownerRule(rules, 'body.charts-page .home-toolbar .export-buttons .export-scope-note');
    assert.equal(row.get('flex-direction'), 'column', `${width}px: actual button and note must have distinct rows`); assert.equal(row.get('width'), '100%');
    assert.ok(btn.get('flex-shrink') === '0' || btn.get('flex') === '0 0 auto' || btn.get('flex') === 'none', `${width}px: export button must not shrink`); assert.equal(btn.get('max-width'), '100%'); assert.equal(btn.get('white-space'), 'normal');
    assert.equal(caption.get('width'), '100%'); assert.equal(caption.get('white-space'), 'normal');
  }
});

function acceptanceNyt(mobile, fields = {}, locale = 'zh') {
  const book = { ...sampleBook, title: 'DEAD BEAT', title_zh: '亡者之歌', author: 'Leigh Bardugo', publisher: 'Publisher', cover: '', _original_cover: '', description: 'Only English introduction.', description_zh: '唯一中文简介。', details: '', details_zh: '', ...fields };
  const back = '/?category=hardcover-fiction&lang=' + locale + '&view=compact&page=2';
  return render((mobile ? 'mobile/' : '') + 'book_detail.html', { book, book_index: 0, category: 'hardcover-fiction', categories: { 'hardcover-fiction': '小说' }, category_names_en: { 'hardcover-fiction': 'Hardcover Fiction' }, back_url: back }, '/book/0?category=hardcover-fiction&lang=' + locale, locale);
}
for (const mobile of [false, true]) {
  test(`live acceptance ${mobile ? 'mobile' : 'desktop'} NYT keeps one bilingual intro without contradictory missing-details notice`, () => {
    for (const locale of ['zh', 'en']) {
      const result = acceptanceNyt(mobile, {}, locale); const content = result.nodes.filter(node => isContentNode(result, node));
      assert.equal(content.some(node => node.ownText.trim() === '暂无更多信息' || node.ownText.trim() === 'No further information'), false);
      assert.equal(content.filter(node => node.tag === 'p' && node.ownText.trim() === (locale === 'zh' ? '唯一中文简介。' : 'Only English introduction.')).length, 1);
      assert.equal(content.filter(node => hasClass(node, mobile ? 'm-detail-empty' : 'detail-intro-empty')).length, 0);
      assert.equal(content.some(node => node.tag === 'button' && node.attrs['data-tab'] === 'details'), false);
      assert.ok(content.some(node => node.ownText.includes(sampleBook.isbn13)), 'visible ISBN retained');
      assert.ok(content.some(node => node.tag === 'a' && node.attrs.href === '/?category=hardcover-fiction&lang=' + locale + '&view=compact&page=2'), 'safe return target retained');
      if (!mobile) {
        const intro = content.find(node => hasClass(node, 'detail-intro-text')); assert.equal(intro.attrs['data-intro-zh'], '唯一中文简介。'); assert.equal(intro.attrs['data-intro-en'], 'Only English introduction.');
        assert.ok(content.some(node => node.tag === 'button' && node.attrs['data-toggle-original'] === 'desc'), 'original-language toggle retained');
        assert.ok(content.some(node => node.attrs.id === 'desc-en' && hasClass(node, 'lang-toggle-content') && node.text === 'Only English introduction.'));
      }
    }
  });
  test(`live acceptance ${mobile ? 'mobile' : 'desktop'} NYT empty and canonical placeholder fields produce one specific empty state`, () => {
    const cases = [
      { description: '', description_zh: '', details: '', details_zh: '' },
      { description: 'No summary available.', description_zh: '暂无简介', details: 'No detailed description available.', details_zh: '暂无详细描述' },
      { description: null, description_zh: null, details: '英文', details_zh: '- 英文' },
    ];
    for (const fields of cases) for (const locale of ['zh', 'en']) {
      const result = acceptanceNyt(mobile, fields, locale); const content = result.nodes.filter(node => isContentNode(result, node));
      const empty = content.filter(node => hasClass(node, mobile ? 'm-detail-empty' : 'detail-intro-empty'));
      assert.equal(empty.length, 1, `${locale}: missing/placeholder data must have exactly one empty state`); assert.ok(empty[0].text.trim());
      assert.ok(['暂无简介', '暂无更多信息', 'No introduction available', 'No further information'].includes(empty[0].text.trim()), 'missing message must be specific');
      assert.equal(content.some(node => node.tag === 'button' && node.attrs['data-tab'] === 'details'), false);
      assert.equal(content.some(node => hasClass(node, 'detail-intro-text') || hasClass(node, 'm-detail-text')), false);
      for (const literal of ['No summary available.', 'No detailed description available.', '暂无详细描述', '- 英文']) assert.equal(content.some(node => node.ownText.trim() === literal), false, 'actual placeholder/noise text cannot be shown');
    }
  });
}
test('live acceptance NYT original title and empty-state small text use the readable shared theme role', () => {
  const result = acceptanceNyt(false, { description: '', description_zh: '' });
  assert.ok(result.nodes.some(node => hasClass(node, 'detail-title-en') && node.text === 'DEAD BEAT'));
  const styles = result.nodes.filter(node => node.tag === 'style');
  for (const style of styles) assert.deepEqual(transformSync(style.text, { loader: 'css' }).warnings, [], 'actual rendered CSS must parse without warnings');
  const css = styles.map(node => node.text).join('\n');
  for (const selector of ['.detail-title-en', '.detail-intro-empty']) assert.equal(ownerRule(css, selector).get('color'), 'var(--text-secondary)', selector);
});

test('live acceptance rankings real four-tab navigation starts at the reachable edge on narrow screens', () => {
  for (const tab of ['cross', 'longevity', 'overlooked', 'publishers']) {
    const result = render('rankings.html', { tab, category_count: 5, cross_entries: [], longevity_entries: [], overlooked_entries: [], publisher_entries: [], award_years: [2026], category_names_en: {}, update_time: '2026-09-30' }, '/rankings?tab=' + tab + '&lang=zh');
    const nav = result.nodes.find(node => node.tag === 'nav' && hasClass(node, 'charts-sections') && hasClass(node, 'rankings-tabs')); assert.ok(nav);
    const links = result.nodes.filter(node => node.tag === 'a' && node.ancestors.at(-1) === result.nodes.indexOf(nav)); assert.equal(links.length, 4);
    assert.deepEqual(links.map(node => new URL(node.attrs.href, 'https://bookrank.test').searchParams.get('tab')), ['cross', 'longevity', 'overlooked', 'publishers']);
    assert.equal(links.find(node => node.attrs['aria-current'] === 'page').attrs.href, '/rankings?tab=' + tab + '&lang=zh');
  }
  const css = source('static/css/charts.css');
  assert.deepEqual(transformSync(css, { loader: 'css' }).warnings, [], 'actual charts stylesheet must parse');
  assert.equal(ownerRule(maxWidthCss(css, 1280), 'nav.charts-sections.rankings-tabs').size, 0, 'wide layout unchanged');
  assert.equal(ownerRule(css, '.charts-sections').get('justify-content'), 'center', 'original wide alignment retained');
  for (const width of [320, 390, 768]) {
    const rules = maxWidthCss(css, width); const nav = ownerRule(rules, 'nav.charts-sections.rankings-tabs'); const link = ownerRule(rules, '.charts-sections.rankings-tabs a');
    const alignment = nav.get('justify-content') || ownerRule(css, '.charts-sections').get('justify-content');
    assert.equal(alignment, 'flex-start', `${width}px: center alignment creates unreachable negative scroll overflow`);
    assert.equal(nav.get('overflow-x'), 'auto'); assert.equal(nav.get('flex-wrap'), 'nowrap');
    assert.ok(link.get('flex') === '0 0 auto' || link.get('flex-shrink') === '0'); assert.equal(link.get('white-space'), 'nowrap');
  }
});

test('live acceptance weekly real filter groups search count and clear have independent narrow rows', () => {
  const report = { title: 'Report', report_date: '2026-09-27', week_start: '2026-09-21', week_end: '2026-09-27', content_data: { summary: '' } };
  const result = render('weekly_reports.html', { reports: [report], report_sections: [{ year: 2026, month: 9, reports: [report] }], latest_report: report, is_generating: false }, '/reports/weekly?lang=zh');
  const bar = result.nodes.find(node => hasClass(node, 'filter-controls') && hasClass(node, 'wr-filter-bar')); assert.ok(bar);
  const groups = result.nodes.filter(node => hasClass(node, 'filter-group') && node.ancestors.at(-1) === result.nodes.indexOf(bar)); assert.equal(groups.length, 2);
  const month = result.nodes.find(node => node.attrs.id === 'month-filter'); const search = result.nodes.find(node => node.attrs.id === 'search-input'); assert.ok(ancestors(result, month).includes(groups[0])); assert.ok(ancestors(result, search).includes(groups[1]));
  for (const id of ['wr-filter-count', 'wr-filter-clear']) assert.equal(result.nodes.find(node => node.attrs.id === id).ancestors.at(-1), result.nodes.indexOf(bar));
  const css = result.nodes.filter(node => node.tag === 'style').map(node => node.text).join('\n');
  assert.deepEqual(transformSync(css, { loader: 'css' }).warnings, [], 'actual weekly rendered style must parse');
  assert.equal(ownerRule(maxWidthCss(css, 1280), '.weekly-page .filter-controls.wr-filter-bar').size, 0, 'wide filter unchanged');
  for (const width of [320, 390, 768]) {
    const rules = maxWidthCss(css, width); const row = ownerRule(rules, '.weekly-page .filter-controls.wr-filter-bar'); const group = ownerRule(rules, '.weekly-page .filter-controls.wr-filter-bar>.filter-group'); const box = ownerRule(rules, '.weekly-page .wr-filter-bar .search-box'); const input = ownerRule(rules, '.weekly-page .wr-filter-bar .search-box .form-input');
    assert.equal(row.get('display'), 'grid', `${width}px: wrapped flex groups collide with intrinsic search width`); assert.equal(row.get('grid-template-columns'), 'minmax(0,1fr)');
    assert.equal(group.get('min-width'), '0'); assert.equal(group.get('width'), '100%'); assert.equal(box.get('min-width'), '0'); assert.equal(box.get('width'), '100%'); assert.equal(box.get('position'), 'static'); assert.equal(box.get('transform'), 'none');
    assert.equal(input.get('min-width'), '0'); assert.ok(input.get('flex')); assert.equal(ownerRule(rules, '.weekly-page .wr-filter-bar .search-btn').get('flex'), '0 0 44px');
  }
});

test('live acceptance weekly decline SVG use resolves to one nonempty downward symbol in actual SSR', () => {
  const result = render('weekly_report_detail.html', { report: { title: 'Report', week_start: '2026-09-21', week_end: '2026-09-27', report_date: '2026-09-27', created_at: '2026-09-27T12:00:00' }, content: { total_falling_display: 2, top_changes: [], new_books: [], featured_books: [] }, safe_summary: '' }, '/reports/weekly/2026-09-27?lang=zh');
  const uses = result.nodes.filter(node => node.tag === 'use' && node.attrs.href === '#icon-arrow-down'); assert.ok(uses.length);
  const symbols = result.nodes.filter(node => node.tag === 'symbol' && node.attrs.id === 'icon-arrow-down'); assert.equal(symbols.length, 1, 'referenced decline icon must exist once in rendered sprite');
  const symbol = symbols[0]; const up = result.nodes.find(node => node.tag === 'symbol' && node.attrs.id === 'icon-arrow-up'); assert.ok(up);
  for (const attr of ['viewbox', 'fill', 'stroke', 'stroke-width', 'stroke-linecap', 'stroke-linejoin']) assert.equal(symbol.attrs[attr], up.attrs[attr]);
  const geometry = result.nodes.filter(node => node.ancestors.includes(result.nodes.indexOf(symbol)) && ['line', 'polyline', 'path'].includes(node.tag)); assert.ok(geometry.length >= 2);
  const head = geometry.find(node => node.tag === 'polyline'); assert.ok(head); const points = head.attrs.points.trim().split(/[ ,]+/).map(Number); assert.equal(points.length, 6); assert.ok(points.every(Number.isFinite)); assert.ok(points[3] > points[1] && points[3] > points[5], 'arrow head must point downward');
});
