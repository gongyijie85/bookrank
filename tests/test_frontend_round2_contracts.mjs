import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { spawnSync } from 'node:child_process';
const repo = process.env.ROUND2_ROOT || path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');
const renderCode = String.raw`
import json,sys,importlib.util
from pathlib import Path
from flask import Flask
from jinja2 import ChoiceLoader,DictLoader,FileSystemLoader
from html.parser import HTMLParser
sys.stdin.reconfigure(encoding='utf-8');sys.stdout.reconfigure(encoding='utf-8')
x=json.load(sys.stdin);root=Path(x['root']);helper=Path(x['helper']);spec=importlib.util.spec_from_file_location('actual_book_labels',helper);mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
a=Flask(__name__,static_folder='static')
for endpoint,rule in [('index','/'),('new_books','/new-books'),('awards','/awards'),('profile','/profile'),('rankings','/rankings'),('book_detail','/book/<int:book_index>'),('new_book_detail','/new-book/<int:book_id>'),('award_book_detail','/award-book/<int:book_id>'),('award_book_cover','/award-book/<int:book_id>/cover')]: a.add_url_rule(rule,endpoint='main.'+endpoint,view_func=lambda:'')
base='{% block title %}{% endblock %}{% block header %}{% endblock %}{% block content %}{% endblock %}{% block extra_js %}{% endblock %}'
a.jinja_loader=ChoiceLoader([DictLoader({'base.html':base,'mobile/base.html':base}),FileSystemLoader(str(root/'templates'))]);e=a.jinja_env
for name in ['award_result_kind','price_display']: e.filters[name]=getattr(mod,name)
e.filters['bilingual']=lambda zh,en='',*args:(en or zh) if x['locale']=='en' else (zh or en)
for name in ['award_term','category_name','language_name','cover_src','cover_src_or_default','sanitize_html']:e.filters[name]=lambda v,*args:v or ''
e.filters['publication_state']=lambda v:'pending';e.filters['publication_state_label']=lambda v,*args:'Pending'
e.globals.update({'_':lambda s,**kw:s%kw if kw else s,'gettext':lambda s,**kw:s%kw if kw else s,'get_locale':lambda:x['locale'],'csp_nonce':lambda:'TEST','split_volume_marker':lambda v:(v or '',''),'PLACEHOLDER_TEXTS':[],'is_non_substantive_details':lambda v:False})
class DOM(HTMLParser):
 def __init__(self):super().__init__();self.nodes=[];self.stack=[]
 def handle_starttag(self,tag,attrs):
  i=len(self.nodes);self.nodes.append({'tag':tag,'attrs':dict(attrs),'text':''});
  if tag not in ['img','input','br','hr','meta','link','use']:self.stack.append(i)
 def handle_endtag(self,tag):
  for j in range(len(self.stack)-1,-1,-1):
   if self.nodes[self.stack[j]]['tag']==tag:self.stack=self.stack[:j];break
 def handle_data(self,t):
  for i in self.stack:self.nodes[i]['text']+=t
with a.test_request_context(x['url']):
 t=e.from_string(x['fragment']) if x.get('fragment') else e.get_template(x['name']);html=t.render(**x['context']);dom=DOM();dom.feed(html);print(json.dumps({'html':html,'nodes':dom.nodes},ensure_ascii=False))
`;
function render(name, context, { locale = 'zh', url = '/new-books?lang=zh&view=list&page=3&search=rain&publication_status=pending', fragment } = {}) {
  const helper = process.env.ROUND2_LABELS_PATH || path.join(repo, 'app/utils/book_labels.py');
  const result = spawnSync(process.env.PYTHON || 'python', ['-c', renderCode], { input: JSON.stringify({ root: repo, helper, name, context, locale, url, fragment }), encoding: 'utf8', maxBuffer: 12 * 1024 * 1024 });
  assert.equal(result.error, undefined); assert.equal(result.status, 0, result.stderr); return JSON.parse(result.stdout);
}
const hasClass = (node, name) => (node.attrs.class || '').split(/\s+/).includes(name);
const book = { id: 7, title: 'Original title', title_en: 'Original title', title_zh: '译名', author: 'Author', isbn13: '9780000000007', isbn10: null, cover_url: '', cover_local_path: '', cover_original_url: '', category: 'Fiction', award_wikidata_id: null, year: 2026, publisher: { id: 1, name: '出版社', name_en: 'Publisher' }, price: 0, publication_date: null, is_recently_published: false, description: '', description_zh: '', details: '', rank: 1, award_name: 'Award', award_name_en: 'Award', award: { name: 'Award', name_en: 'Award', wikidata_id: null } };
for (const locale of ['zh', 'en']) test(`actual SSR macro detail URL explicitly preserves ${locale}, source conditions and numeric zero price`, () => {
  const url = '/new-books?lang=' + locale + '&view=list&page=3&search=rain&publication_status=pending';
  const result = render('', { book }, { locale, url, fragment: '{% from "_macros.html" import new_book_card %}{{ new_book_card(book) }}' });
  const detail = result.nodes.find(n => n.tag === 'a' && (n.attrs.href || '').startsWith('/new-book/7'));
  assert.ok(detail); const target = new URL(detail.attrs.href, 'https://bookrank.test');
  assert.equal(target.searchParams.get('lang'), locale); assert.equal(target.searchParams.get('return_to'), url);
  const price = result.nodes.find(n => Object.hasOwn(n.attrs, 'data-price-raw')); assert.ok(price); assert.equal(price.attrs['data-price-raw'], '0');
  assert.equal(price.text.trim(), locale === 'zh' ? '0（币种未确认）' : '0 (currency unconfirmed)');
});
for (const mobile of [false, true]) test(`profile ${mobile ? 'mobile' : 'desktop'} actual SSR keeps real known routes, localized title and ISBN`, () => {
  for (const locale of ['zh', 'en']) {
    const fav = { isbn: '9780385550369', title: locale === 'en' ? 'James' : '詹姆斯', title_en: 'James', title_zh: '詹姆斯', author: 'Percival Everett', detail_url: '/award-book/31?lang=' + locale + '&return_to=%2Fprofile%3Flang%3D' + locale };
    const result = render(mobile ? 'mobile/profile.html' : 'profile.html', { favorites: [fav], search_history: [], reading_history: [] }, { locale, url: '/profile?lang=' + locale });
    const title = result.nodes.find(n => Object.hasOwn(n.attrs, 'data-profile-title-en')); assert.ok(title); assert.equal(title.text.trim(), fav.title);
    const link = mobile ? result.nodes.find(n => n.tag === 'a' && hasClass(n, 'm-profile-book-link')) : title; assert.ok(link); assert.equal(link.attrs.href, fav.detail_url);
    assert.ok(result.nodes.some(n => n.tag === 'p' && n.text.trim() === fav.isbn));
    assert.equal(result.html.includes('/?search=%E8%A9%B9'), false);
  }
});
const rankingContext = { tab: 'overlooked', category_count: 19, category_names_en: {}, update_time: '2026-09-30', cross_entries: [], longevity_entries: [], overlooked_entries: [], publisher_entries: [], award_years: [2026, 2025, 2024], rankings_nyt_unavailable_count: 2, rankings_awards_unavailable: true };
for (const mobile of [false, true]) test(`four rankings ${mobile ? 'mobile' : 'desktop'} real SSR distinguishes unknown/empty and keeps partial cards`, () => {
  const name = mobile ? 'mobile/rankings.html' : 'rankings.html';
  for (const tab of ['cross', 'longevity', 'overlooked', 'publishers']) {
    const result = render(name, { ...rankingContext, tab }, { url: '/rankings?lang=zh&tab=' + tab });
    assert.ok(result.nodes.some(n => (n.tag === 'h2' || n.tag === 'p') && n.text.trim() === '暂无法完整读取榜单'), tab + ' failed source must not be an empty count');
    assert.ok(result.nodes.some(n => n.tag === 'a' && n.attrs.href === '/rankings?lang=zh&tab=' + tab && n.text === '重新加载'));
    if (tab === 'overlooked') {
      assert.equal(result.html.includes('2026、2025、2024'), true);
      assert.equal(result.html.includes('未出现仅指可读取分类，来源不完整，暂无法核对全部分类'), true);
      assert.equal(result.html.includes('部分奖项年份记录暂不可读取'), true);
    }
    const success = render(name, { ...rankingContext, tab, rankings_nyt_unavailable_count: 0, rankings_awards_unavailable: false });
    assert.equal(success.nodes.some(n => n.attrs.role === 'status'), false);
    assert.equal(success.html.includes('暂无法完整读取榜单'), false);
  }
  const entry = { id: 31, title: 'Candidate', title_zh: '候选', author: 'Author', cover_local_path: '', cover_original_url: '', awards: [{ award_name: 'Award', award_name_en: 'Award', year: 2026, category: 'Fiction', wikidata_id: null }] };
  const partial = render(name, { ...rankingContext, overlooked_entries: [entry] }, { url: '/rankings?tab=overlooked&lang=zh' });
  assert.ok(partial.nodes.some(n => n.tag === 'a' && (n.attrs.href || '').startsWith('/award-book/31')));
  assert.equal(partial.html.includes('候选'), true); assert.equal(partial.html.includes('暂无法完整读取榜单'), false, 'error hint must retain partial cards without adding a false empty panel');
});
test('real award label helper and reusable source macro distinguish explicit outcomes including author honors', () => {
  const cases = [ ['winner', null, '作品获奖'], ['shortlist', null, '作品入围'], ['Fiction', 'Q37922', '作者荣誉（非作品获奖）'], ['Fiction', null, '奖项记录（结果未注明）'] ];
  for (const [category, id, expected] of cases) {
    const result = render('', { category, id, rank: 1 }, { fragment: '{% from "_macros.html" import award_result_label %}{{ award_result_label(category|award_result_kind(id)) }}' });
    const label = result.nodes.find(n => hasClass(n, 'award-result')); assert.ok(label); assert.equal(label.text, expected);
  }
  for (const [reason, expected] of [['same_author', '同作者'], ['same_award', '同奖项'], ['other_award', '其他奖项'], ['adjacent_year', '']]) {
    const result = render('', { reason }, { fragment: '{% from "_macros.html" import related_reason_label %}{{ related_reason_label(reason) }}' });
    const label = result.nodes.find(n => hasClass(n, 'related-reason')); assert.equal(label?.text || '', expected);
  }
});
test('awards auxiliary catalog/count failures render unavailable instead of false zero', () => {
  for (const name of ['templates/awards.html', 'templates/mobile/awards.html']) {
    const text = fs.readFileSync(path.join(repo, name), 'utf8');
    const headerStart = text.indexOf(name.includes('/mobile/') ? '<span class="m-top-nav-subtitle">' : '<header class="page-header">');
    const headerEnd = text.indexOf(name.includes('/mobile/') ? '</span>' : '</header>', headerStart); assert.ok(headerStart >= 0 && headerEnd > headerStart);
    const output = render('', { total_books: 3, data_load_failed: false, awards: [], awards_unavailable: true, selected_award: 'Booker', selected_year: 2026 }, { fragment: text.slice(headerStart, headerEnd) });
    assert.equal(output.html.includes('奖项目录暂不可用'), true); assert.equal(output.html.includes('0 个奖项'), false); assert.equal(output.html.includes('3 本图书'), true);
  }
  const text = fs.readFileSync(path.join(repo, 'templates/awards.html'), 'utf8'); const start = text.indexOf('<span class="award-tile-count">'); const end = text.indexOf('</span>', start) + 7; assert.ok(start >= 0 && end > start);
  for (const value of [null, 0, 3]) {
    const output = render('', { award: { book_count: value }, award_counts_unavailable: value === null }, { fragment: text.slice(start, end) });
    assert.equal(output.nodes[0].text.trim(), value === null ? '数量暂不可用' : value + ' 本图书');
  }
});
