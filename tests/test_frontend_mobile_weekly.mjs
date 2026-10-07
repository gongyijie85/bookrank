import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';
import { transformSync } from 'esbuild';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
function render(name, context, locale = 'en') {
  const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root: repo, name, context, locale, url: '/reports/weekly?lang=' + locale }),
    encoding: 'utf8', maxBuffer: 8 * 1024 * 1024, env: { ...process.env, FLASK_ENV: 'testing' },
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
const hasClass = (node, name) => (node.attrs.class || '').split(/\s+/).includes(name);
const report = { title: '中文原始周报标题', week_start: '2026-09-21', week_end: '2026-09-27', report_date: '2026-09-27', created_at: '2026-09-28T12:34:00', updated_at: null, content_data: { title_display: 'Weekly Bestseller Report', summary: 'September summary' } };
function rules(css, selector) {
  const compact = transformSync(css, { loader: 'css', legalComments: 'none', minifyWhitespace: true }).code;
  const declarations = compact.split('}').map(block => {
    const boundary = block.lastIndexOf('{'); return { selector: block.slice(0, boundary).trim(), value: block.slice(boundary + 1) };
  }).filter(rule => rule.selector === selector).map(rule => rule.value).join(';');
  return new Map(declarations.split(';').filter(value => value.includes(':')).map(value => {
    const boundary = value.indexOf(':'); return [value.slice(0, boundary).trim(), value.slice(boundary + 1).trim()];
  }));
}

test('mobile weekly real intro reserves the fixed 44px controls row without excessive blank space', () => {
  const result = render('mobile/weekly_reports.html', { reports: [report], latest_report: report, report_sections: [{ year: 2026, month: 9, reports: [report] }], is_generating: false });
  const intro = result.nodes.find(node => hasClass(node, 'm-report-intro')); assert.ok(intro);
  const input = result.nodes.find(node => node.attrs.id === 'm-search-input'); assert.ok(input);
  assert.ok(result.nodes.some(node => node.attrs.id === 'm-theme-toggle'));
  assert.ok(result.nodes.some(node => node.attrs.id === 'm-lang-globe'));
  const css = readFileSync(path.join(repo, 'static/mobile/css/mobile.css'), 'utf8');
  const root = rules(css, ':root');
  const numeric = value => {
    let resolved = value;
    for (let depth = 0; depth < 8 && resolved.includes('var('); depth++) resolved = resolved.replace(/var\((--[\w-]+)\)/g, (_, name) => { assert.ok(root.has(name)); return root.get(name); });
    resolved = resolved.replace(/env\([^)]*\)/g, '0px').replace(/calc\(/g, '(').replace(/px/g, '');
    assert.match(resolved, /^[\d.\s()+*/-]+$/); return vm.runInNewContext(resolved);
  };
  const introStyles = new Map([...rules(css, '.m-report-intro'), ...rules(result.nodes.filter(node => node.tag === 'style').map(node => node.text).join('\n'), '.m-report-intro'), ...rules('.m-report-intro{' + (intro.attrs.style || '') + '}', '.m-report-intro')]);
  const shorthand = rules(css, '.m-report-intro').get('padding').split(' ');
  const paddingTop = numeric(introStyles.get('padding-top') || shorthand[0]);
  const headerHeight = numeric(rules(css, '.m-header').get('height'));
  const countHeight = numeric(rules(css, '.m-report-intro-count').get('font-size')) * 1.5;
  const filterTop = headerHeight + paddingTop + countHeight + numeric(shorthand[2] || shorthand[0]);
  const toolbar = rules(css, '.m-theme-toggle-btn');
  const toolbarBottom = numeric(toolbar.get('top')) + numeric(toolbar.get('height'));
  assert.ok(headerHeight + paddingTop >= toolbarBottom, 'intro content must begin below the fixed controls row');
  assert.ok(filterTop >= toolbarBottom + numeric(root.get('--space-2')), 'search/month row must clear the fixed controls');
  assert.ok(paddingTop <= toolbarBottom - headerHeight + numeric(root.get('--space-4')), 'reserve one row without pushing the first report away with a large spacer');
  assert.equal(result.nodes.filter(node => hasClass(node, 'm-report-card')).length, 1);
  // This source/SSR spacing contract is not a browser geometry or real-device test.
});

test('mobile weekly month and keyword still filter the same rendered report cards', () => {
  const other = { ...report, title: 'Older title', week_start: '2026-08-24', week_end: '2026-08-30', report_date: '2026-08-30', content_data: { title_display: 'August Report', summary: 'Older summary' } };
  const result = render('mobile/weekly_reports.html', { reports: [report, other], latest_report: report, report_sections: [{ year: 2026, month: 9, reports: [report] }, { year: 2026, month: 8, reports: [other] }], is_generating: false });
  const cards = result.nodes.filter(node => hasClass(node, 'm-report-card')).map(node => ({ style: {}, getAttribute: name => node.attrs[name] || '', querySelector(selector) { return { textContent: selector === '.m-report-title' ? node.attrs['data-title'] : node.attrs['data-summary'] }; } }));
  const control = () => ({ value: '', listeners: {}, addEventListener(type, handler) { this.listeners[type] = handler; } });
  const month = control(); month.options = [{ value: '' }, { value: '2026-09' }, { value: '2026-08' }];
  const search = control(); const clear = control(); const count = { textContent: '' }; const empty = { style: {} };
  const ids = { 'm-month-filter': month, 'm-search-input': search, 'm-wr-filter-clear': clear, 'm-wr-filter-count': count, 'm-wr-no-results': empty };
  let ready;
  const code = result.nodes.find(node => node.tag === 'script' && node.text.includes('var monthFilter =')).text;
  vm.runInNewContext(code, { URL, URLSearchParams, history: { replaceState() {} }, window: { location: { href: 'https://bookrank.example/reports/weekly?lang=en', search: '?lang=en' }, addEventListener() {} }, document: { documentElement: { getAttribute: () => 'en' }, getElementById: id => ids[id], querySelectorAll: selector => selector === '.m-report-card' ? cards : [], addEventListener(type, handler) { if (type === 'DOMContentLoaded') ready = handler; } } });
  ready(); month.value = '2026-09'; search.value = 'weekly'; search.listeners.input();
  assert.deepEqual(cards.map(card => card.style.display), ['', 'none']); assert.match(count.textContent, /^1 /);
  search.value = 'absent'; search.listeners.input(); assert.deepEqual(cards.map(card => card.style.display), ['none', 'none']); assert.equal(empty.style.display, 'block');
  clear.listeners.click(); assert.deepEqual(cards.map(card => card.style.display), ['', '']); assert.match(count.textContent, /^2 /);
});

function detailTitleNodes(title, prepared) {
  const result = render('mobile/weekly_report_detail.html', { report: { ...report, title }, content: { title_display: prepared }, safe_summary: '' });
  return { result, title: result.nodes.find(node => node.tag === 'title'), og: result.nodes.find(node => node.tag === 'meta' && node.attrs.property === 'og:title'), twitter: result.nodes.find(node => node.tag === 'meta' && node.attrs.name === 'twitter:title'), share: result.nodes.find(node => Object.hasOwn(node.attrs, 'data-share-title')), hero: result.nodes.find(node => hasClass(node, 'm-report-hero-period')) };
}
test('mobile weekly English detail title and share metadata use prepared display title', () => {
  const expected = 'Weekly Bestseller Report & Snapshot'; const nodes = detailTitleNodes(report.title, expected);
  assert.equal(nodes.hero.text.trim(), expected); assert.equal(nodes.title.text, expected + ' - BookRank');
  assert.equal(nodes.og.attrs.content, expected + ' - BookRank'); assert.equal(nodes.twitter.attrs.content, expected + ' - BookRank'); assert.equal(nodes.share.attrs['data-share-title'], expected);
});
test('mobile weekly legacy detail without a prepared title preserves the original title or existing fallback', () => {
  for (const [title, prepared, expected] of [['Legacy custom report', undefined, 'Legacy custom report'], ['Legacy custom report', '', 'Legacy custom report'], ['', undefined, '周报']]) {
    const nodes = detailTitleNodes(title, prepared);
    assert.equal(nodes.hero.text.trim(), expected); assert.equal(nodes.title.text, expected + ' - BookRank'); assert.equal(nodes.share.attrs['data-share-title'], expected);
  }
});
