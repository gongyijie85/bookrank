import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
import vm from 'node:vm';

const repo = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
function render(name, context, url, locale = 'en') {
  const result = spawnSync(process.env.PYTHON || 'python', [path.join(repo, 'tests/fixtures/render_audit_followup.py')], {
    input: JSON.stringify({ root: repo, name, context, url, locale }), encoding: 'utf8', maxBuffer: 8 * 1024 * 1024,
    env: { ...process.env, FLASK_ENV: 'testing' },
  });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr);
  return JSON.parse(result.stdout);
}
const book = { id: 2351, title: 'Full original title', title_zh: '完整书名', author: 'Author', isbn13: '9780525556657', isbn10: '', cover_url: '', cover: '', _original_cover: '', category: 'Fiction', publisher: { id: 1, name: '出版社', name_en: 'Publisher' }, publication_date: null, publication_dt: '', price: null, page_count: 123, language: 'en', description: 'English introduction', description_zh: '中文简介', details: '', details_zh: '', category_name: 'Fiction', list_name: 'Fiction', weeks_on_list: 2 };

test('mobile new-book detail renders actual decoded JSON purchase links and no links from invalid JSON', () => {
  const href = 'https://books.google.com/books?id=public-fixture';
  for (const raw of [JSON.stringify([{ name: 'Google Books', url: href }]), '', '{invalid', '{}']) {
    const result = render('mobile/new_book_detail.html', { book: { ...book, buy_links: raw }, back_url: '/new-books?lang=en' }, '/new-book/2351?lang=en');
    const purchase = result.nodes.filter(node => node.tag === 'a' && (node.attrs.class || '').includes('m-btn-outline'));
    if (raw.startsWith('[')) {
      assert.equal(purchase.length, 1); assert.equal(purchase[0].attrs.href, href); assert.equal(purchase[0].text, 'Google Books');
      assert.equal(purchase[0].attrs.target, '_blank'); assert.equal(purchase[0].attrs.rel, 'noopener noreferrer');
    } else assert.equal(purchase.length, 0);
  }
});

test('real NYT detail language initialization survives denied reads and continues metadata language updates', () => {
  for (const [url, locale, expected, preferred] of [['/book/0?lang=en', 'en', ['en']], ['/book/0', 'en', ['en']], ['/book/0?lang=english', 'zh', []], ['/book/0', 'zh', ['en'], true]]) {
    const result = render('book_detail.html', { book: { ...book, publisher: 'Publisher', buy_links: [] }, book_index: 0, category: 'fiction', categories: { fiction: '小说' }, category_names_en: { fiction: 'Fiction' }, back_url: '/?lang=en' }, url, locale);
    const start = result.html.indexOf('(function initDetailLang()'); const end = result.html.indexOf('})();', start); assert.ok(start >= 0 && end > start);
    const category = { textContent: '小说', dataset: { catZh: '小说', catEn: 'Fiction' } };
    const language = { textContent: '英语', dataset: { langZh: '英语', langEn: 'English' } };
    const calls = [];
    const context = vm.createContext({
      URLSearchParams, window: { location: { search: new URL(url, 'https://bookrank.example').search } },
      document: { documentElement: { lang: locale === 'en' ? 'en' : 'zh-CN' }, querySelector(selector) { return selector.includes('data-cat-zh') ? category : selector.includes('data-lang-zh') ? language : null; } },
      localStorage: { getItem(key) { if (preferred && key === 'app_language') return 'en'; throw Object.assign(new Error('Denied storage'), { name: 'SecurityError' }); } },
      switchDetailLang(lang) { calls.push(lang); },
    });
    assert.doesNotThrow(() => vm.runInContext(result.html.slice(start, end + 5), context));
    assert.deepEqual(calls, expected);
    context.switchDetailLang('en'); assert.equal(category.textContent, 'Fiction'); assert.equal(language.textContent, 'English');
    context.switchDetailLang('zh'); assert.equal(category.textContent, '小说'); assert.equal(language.textContent, '英语');
  }
});

const mobileSource = readFileSync(path.join(repo, 'static/mobile/js/mobile.js'), 'utf8');
const fallbackStart = mobileSource.indexOf('    const COVER_FALLBACK ='); const fallbackEnd = mobileSource.indexOf('    // ===== 4b.', fallbackStart);
assert.ok(fallbackStart >= 0 && fallbackEnd > fallbackStart);
for (const tab of ['cross', 'longevity', 'overlooked']) test(`real mobile ${tab} cover falls back on image failure before or after script initialization`, () => {
  const missing = '/fixture-missing-cover.png';
  const entry = { id: 7, title: 'Cover fixture', title_zh: '', author: 'Author', cover: missing, cover_local_path: missing, cover_original_url: '', category_count: 2, best_rank: 3, total_weeks: 6, source_index: 0, source_category: 'fiction', listings: [], awards: [] };
  const result = render('mobile/rankings.html', { tab, category_count: 13, category_names_en: {}, cross_entries: tab === 'cross' ? [entry] : [], longevity_entries: tab === 'longevity' ? [entry] : [], overlooked_entries: tab === 'overlooked' ? [entry] : [], publisher_entries: [], award_years: [2026], nyt_failures: 0, awards_failed: false }, '/rankings?tab=' + tab + '&lang=en');
  const rendered = result.nodes.find(node => node.tag === 'img' && node.attrs.src === missing); assert.ok(rendered);
  for (const failedBeforeScript of [false, true]) {
    const img = { tagName: 'IMG', src: missing, dataset: {}, complete: failedBeforeScript, naturalWidth: 0, hasAttribute: name => Object.hasOwn(rendered.attrs, name) };
    let listener;
    const context = vm.createContext({ window: {}, document: { addEventListener(type, callback, capture) { if (type === 'error') { listener = callback; assert.equal(capture, true); } }, querySelectorAll: () => img.hasAttribute('data-cover-fallback') ? [img] : [] } });
    vm.runInContext(mobileSource.slice(fallbackStart, fallbackEnd) + '\ninitImageFallback();', context);
    if (!failedBeforeScript) listener({ target: img });
    assert.equal(img.src, '/static/default-cover.png');
    img.src = '/after-first-fallback.png'; listener({ target: img }); assert.equal(img.src, '/after-first-fallback.png', 'error fallback must remain guarded against a loop');
  }
});
