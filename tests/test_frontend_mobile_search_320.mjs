import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import { transformSync } from 'esbuild';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const css = transformSync(readFileSync(path.join(repo, 'static/mobile/css/mobile.css'), 'utf8'), {
  loader: 'css', minifyWhitespace: true, legalComments: 'none',
}).code;
function styles(...selectors) {
  const declarations = new Map();
  for (const block of css.split('}')) {
    const boundary = block.lastIndexOf('{');
    const names = block.slice(0, boundary).trim().split(',').map(value => value.trim());
    if (!names.some(name => selectors.includes(name))) continue;
    for (const value of block.slice(boundary + 1).split(';')) {
      const colon = value.indexOf(':');
      if (colon > 0) declarations.set(value.slice(0, colon).trim(), value.slice(colon + 1).trim());
    }
  }
  return declarations;
}
function render(name, context, locale) {
  const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_ux_round3.py')], {
    input: JSON.stringify({ root: repo, name, context, locale, url: '/?lang=' + locale, actual_display_labels: true }),
    encoding: 'utf8', maxBuffer: 12 * 1024 * 1024,
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
const hasClass = (node, name) => (node.attrs.class || '').split(/\s+/).includes(name);
const within = (result, node, owner) => node.ancestors.includes(result.nodes.indexOf(owner));
const homepage = { books: [], categories: { 'hardcover-fiction': '精装小说' }, current_category: 'hardcover-fiction', category_names_en: { 'hardcover-fiction': 'Hardcover Fiction' }, search_query: '', is_cached: false };

test('expanded mobile homepage form may shrink as a child of the actual flex search bar at 320px', () => {
  assert.equal(styles('.m-search-bar').get('display'), 'flex');
  const form = styles('#m-search-bar form');
  assert.equal(form.get('min-width'), '0', 'the flex item must not retain its content minimum');
  assert.match(form.get('flex') || '', /^1(?:\s|$)/, 'the form must take the available search-bar width');
  assert.doesNotMatch(form.get('overflow') || '', /hidden|clip/, 'do not mask horizontal overflow');
});

test('expanded homepage search input can shrink rather than forcing its intrinsic width beyond the viewport', () => {
  const input = styles('.m-search-input');
  assert.equal(input.get('min-width'), '0');
  assert.match(input.get('flex') || '', /^1(?:\s|$)/);
  assert.doesNotMatch(input.get('overflow') || '', /hidden|clip/);
  assert.doesNotMatch(styles('.m-search-bar').get('overflow') || '', /hidden|clip/);
  // These are real owner CSS constraints, not browser geometry or real-device acceptance.
});

test('expanded homepage keeps a nonshrinking search action and 44px controls', () => {
  const button = styles('button', '.m-search-submit');
  const root = styles(':root');
  assert.equal(button.get('flex-shrink'), '0');
  assert.equal(button.get('min-height'), '44px');
  assert.equal(root.get('--input-height'), '44px');
  assert.equal(styles('.m-search-input').get('height'), 'var(--input-height)');
});

for (const locale of ['en', 'zh']) {
  test(`actual homepage SSR search remains a named GET form with localized action (${locale})`, () => {
    const result = render('mobile/index.html', homepage, locale);
    const bar = result.nodes.find(node => node.attrs.id === 'm-search-bar'); assert.ok(bar);
    const form = result.nodes.find(node => node.tag === 'form' && within(result, node, bar)); assert.ok(form);
    assert.equal(form.attrs.action, '/'); assert.equal(form.attrs.method, 'get'); assert.equal(form.attrs.role, 'search');
    const input = result.nodes.find(node => node.attrs.id === 'm-search-input'); assert.ok(within(result, input, form));
    assert.equal(input.attrs.name, 'search'); assert.equal(input.attrs.type, 'search');
    const action = result.nodes.find(node => node.tag === 'button' && within(result, node, form));
    assert.equal(action.attrs.type, 'submit'); assert.equal(action.text.trim(), locale === 'en' ? 'Search' : '搜索');
  });

  test(`rendered mobile CSS and JS cache keys advance together for this search repair (${locale})`, () => {
    const result = render('mobile/index.html', homepage, locale);
    const urls = result.nodes.flatMap(node => {
      const value = node.tag === 'link' ? node.attrs.href : node.tag === 'script' ? node.attrs.src : null;
      if (!value) return [];
      const url = new URL(value, 'https://bookrank.example');
      return ['/static/mobile/css/mobile.css', '/static/mobile/js/mobile.js'].includes(url.pathname) ? [url] : [];
    });
    assert.equal(urls.length, 2);
    for (const url of urls) assert.equal(url.searchParams.get('v'), 'mobile-search-320-20261009');
  });

  for (const reportDate of ['2026-10-08', '2026-10-11']) {
    test(`actual weekly card routes by report date ${reportDate}, preserves ${locale}, and still displays the full week`, () => {
      const report = { title: 'Current week report', week_start: '2026-10-05', week_end: '2026-10-11', report_date: reportDate, created_at: '2026-10-08T12:00:00', updated_at: null, content_data: { title_display: 'Current week report', summary: '' } };
      const result = render('mobile/weekly_reports.html', { reports: [report], latest_report: report, report_sections: [{ year: 2026, month: 10, reports: [report] }], is_generating: false }, locale);
      const card = result.nodes.find(node => node.tag === 'a' && hasClass(node, 'm-report-card')); assert.ok(card);
      const href = new URL(card.attrs.href, 'https://bookrank.example');
      assert.equal(href.pathname, '/reports/weekly/' + reportDate);
      assert.equal(href.searchParams.get('lang'), locale);
      const date = result.nodes.find(node => hasClass(node, 'm-report-sub') && within(result, node, card));
      assert.ok(date); assert.match(date.text, /10\.05\s*-\s*10\.11/);
    });
  }
}
