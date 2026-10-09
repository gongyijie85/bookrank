"""派生榜单真实模板的详情身份与旧链接兼容回归。"""

from urllib.parse import parse_qs, urlsplit

import pytest
from bs4 import BeautifulSoup

from app.utils.template_resolver import render_adaptive


@pytest.mark.parametrize('device', ['desktop', 'mobile'])
@pytest.mark.parametrize('tab', ['cross', 'longevity'])
@pytest.mark.parametrize('locale', ['en', 'zh'])
@pytest.mark.parametrize('isbn', ['9780306406157', ''], ids=['with-isbn', 'without-isbn'])
def test_rankings_detail_links_preserve_identity_and_source(app, device, tab, locale, isbn):
    """ISBN 定位同一本书；无 ISBN 时仍保留旧索引链接和站内返回条件。"""
    category = 'hardcover-nonfiction'
    source_index = 7
    source_path = f'/rankings?tab={tab}&lang={locale}'
    entry = {
        'title': 'A Complete Original Book Title',
        'title_zh': '一本完整图书书名',
        'author': 'Known Author',
        'publisher': 'Known Publisher',
        'cover': '/static/default-cover.png',
        'isbn13': isbn,
        'source_index': source_index,
        'source_category': category,
        'category_count': 2,
        'best_rank': 8,
        'total_weeks': 30,
        'listings': [{'category_id': category, 'category_name': '精装非虚构', 'rank': 8}],
    }
    context = {
        'tab': tab,
        'cross_entries': [entry] if tab == 'cross' else [],
        'longevity_entries': [entry] if tab == 'longevity' else [],
        'overlooked_entries': [],
        'publisher_entries': [],
        'award_years': [2026],
        'category_count': 2,
        'category_names_en': {category: 'Hardcover Nonfiction'},
        'update_time': '2026-10-09 00:00:00',
        'rankings_nyt_unavailable_count': 0,
        'rankings_awards_unavailable': False,
        'rankings_overlooked_loaded': False,
        'active_tab': 'rankings',
    }
    user_agent = (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) Mobile Safari/604.1'
        if device == 'mobile'
        else 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/132.0.0.0 Safari/537.36'
    )
    with app.test_request_context(source_path, headers={'User-Agent': user_agent}):
        html = render_adaptive('rankings.html', **context)

    soup = BeautifulSoup(html, 'html.parser')
    assert bool(soup.select('.m-tabbar')) is (device == 'mobile')
    links = [link for link in soup.select('a[href]') if urlsplit(link['href']).path == f'/book/{source_index}']
    assert len(links) == 2, '封面和书名都应指向详情，同时保留无 ISBN 的旧链接。'
    for link in links:
        parsed = urlsplit(link['href'])
        assert not parsed.netloc
        query = parse_qs(parsed.query, keep_blank_values=True)
        assert query['category'] == [category]
        assert query['lang'] == [locale]
        assert query['return_to'] == [source_path]
        if isbn:
            assert query.get('source_isbn') == [isbn]
        else:
            assert query.get('source_isbn', ['']) == ['']
