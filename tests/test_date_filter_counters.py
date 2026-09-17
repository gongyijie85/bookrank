"""
工单 #83：Google Books 系日期过滤分类拒绝计数器测试

测量"日期缺失保守拒绝"策略的漏报代价：
- 分类函数 _classify_date_filter 的六种类别映射
- get_new_books 主接缝：mock HTTP 响应注入各种日期形态，断言 yield 结果与计数器
- 计数器只测量、不改变任何收录/拒绝行为（与既有 _is_recent_book 布尔判定同构）

所有 HTTP 请求通过 mock session 注入构造响应，测试环境禁止真实网络请求。
"""

from __future__ import annotations

from datetime import date, timedelta
from unittest.mock import MagicMock, patch

from app.services.publisher_crawler.base_crawler import CrawlerConfig, CrawlRequest
from app.services.publisher_crawler.google_books import GoogleBooksCrawler
from app.services.publisher_crawler.google_books_publisher import GoogleBooksPublisherCrawler
from app.services.publisher_crawler.macmillan import MacmillanCrawler


def _today() -> date:
    return date.today()


def _cutoff() -> date:
    return _today() - timedelta(days=GoogleBooksCrawler.RECENCY_WINDOW_DAYS)


def _make_config() -> CrawlerConfig:
    # request_delay=0 避免测试等待；respect_robots_txt=False 避免构造时访问网络
    return CrawlerConfig(request_delay=0, respect_robots_txt=False)


def _mock_google_response(items: list[dict]) -> MagicMock:
    resp = MagicMock(status_code=200)
    resp.json.return_value = {'items': items, 'totalItems': len(items)}
    resp.raise_for_status = MagicMock()
    return resp


def _volume(title: str, published_date: str, isbn: str | None = None) -> dict:
    volume_info: dict = {'title': title, 'authors': ['Test Author'], 'publishedDate': published_date}
    if isbn:
        volume_info['industryIdentifiers'] = [{'type': 'ISBN_13', 'identifier': isbn}]
    return {'id': f'id-{title}', 'volumeInfo': volume_info}


class TestClassifyDateFilter:
    """分类函数六种类别映射（与 _is_recent_book 布尔判定同构）"""

    def test_recent_full_date_accepted(self):
        recent = (_today() - timedelta(days=5)).isoformat()
        assert GoogleBooksCrawler._classify_date_filter(recent, _cutoff()) == 'accepted'

    def test_missing_date_rejected_no_date(self):
        assert GoogleBooksCrawler._classify_date_filter('', _cutoff()) == 'rejected_no_date'

    def test_invalid_value_rejected_unparseable(self):
        assert GoogleBooksCrawler._classify_date_filter('not-a-date', _cutoff()) == 'rejected_unparseable'

    def test_old_date_rejected_out_of_window(self):
        old = (_today() - timedelta(days=200)).isoformat()
        assert GoogleBooksCrawler._classify_date_filter(old, _cutoff()) == 'rejected_out_of_window'

    def test_far_future_rejected_future_placeholder(self):
        far_future = (_today() + timedelta(days=400)).isoformat()
        assert GoogleBooksCrawler._classify_date_filter(far_future, _cutoff()) == 'rejected_future_placeholder'

    def test_year_only_accepted_year_only(self):
        # cutoff 取当年1月1日（与 _compute_cutoff_date(year_from=当年) 一致），
        # 年份-only 按当年1月1日放行并单独计数
        cutoff = date(_today().year, 1, 1)
        assert GoogleBooksCrawler._classify_date_filter(str(_today().year), cutoff) == 'accepted_year_only'

    def test_is_recent_book_stays_isomorphic(self):
        """回归：_is_recent_book 的布尔结论与分类前缀一致，收录/拒绝行为不变"""
        cutoff = _cutoff()
        cases = [
            (_today() - timedelta(days=5)).isoformat(),
            '',
            'not-a-date',
            (_today() - timedelta(days=200)).isoformat(),
            (_today() + timedelta(days=400)).isoformat(),
        ]
        for published in cases:
            category = GoogleBooksCrawler._classify_date_filter(published, cutoff)
            assert GoogleBooksCrawler._is_recent_book(published, cutoff) == category.startswith('accepted')


class TestGetNewBooksCounters:
    """主接缝：注入各种日期形态的 volumes，断言 yield 结果与计数器"""

    def _items(self) -> list[dict]:
        return [
            _volume('Recent Book', (_today() - timedelta(days=5)).isoformat(), '9780000000001'),
            _volume('Year Only Book', str(_today().year), '9780000000002'),
            _volume('No Date Book', '', '9780000000003'),
            _volume('Bad Date Book', 'not-a-date', '9780000000004'),
            _volume('Old Book', '2020-05-01', '9780000000005'),
            _volume('Placeholder Book', (_today() + timedelta(days=400)).isoformat(), '9780000000006'),
        ]

    def test_google_books_crawler_counts_all_categories(self):
        crawler = GoogleBooksCrawler(_make_config())
        crawler._session.get = MagicMock(return_value=_mock_google_response(self._items()))

        # year_from 参数已随接口深化移除：用 _compute_cutoff_date 补丁把
        # cutoff 定在当年1月1日，让年份-only 落在窗口内
        with patch.object(GoogleBooksCrawler, '_compute_cutoff_date', return_value=date(_today().year, 1, 1)):
            books = list(crawler.get_new_books(CrawlRequest(max_books=100)).books)

        assert [b.title for b in books] == ['Recent Book', 'Year Only Book']
        stats = crawler.date_filter_stats
        assert stats['traversed_total'] == 6
        assert stats['rejected_no_date'] == 1
        assert stats['rejected_unparseable'] == 1
        assert stats['rejected_out_of_window'] == 1
        assert stats['rejected_future_placeholder'] == 1
        assert stats['accepted_year_only'] == 1

    def test_counters_start_at_zero(self):
        crawler = GoogleBooksCrawler(_make_config())
        assert all(v == 0 for v in crawler.date_filter_stats.values())

    def test_publisher_crawler_counts_rejections(self):
        class _TestPubCrawler(GoogleBooksPublisherCrawler):
            PUBLISHER_NAME_EN = 'Test Publisher'
            CRAWLER_CLASS_NAME = '_TestPubCrawler'
            SEARCH_QUERIES = ['fiction']

        crawler = _TestPubCrawler(_make_config())
        items = [
            _volume('Recent', (_today() - timedelta(days=3)).isoformat(), '9780000000011'),
            _volume('No Date', '', '9780000000012'),
            _volume('Old', '2019-01-01', '9780000000013'),
        ]
        crawler._session.get = MagicMock(return_value=_mock_google_response(items))

        books = list(crawler.get_new_books(CrawlRequest(max_books=100)).books)

        assert [b.title for b in books] == ['Recent']
        stats = crawler.date_filter_stats
        assert stats['traversed_total'] == 3
        assert stats['rejected_no_date'] == 1
        assert stats['rejected_out_of_window'] == 1

    def test_hachette_counters_accumulate_across_subpublisher_passes(self):
        """HachetteGoogleCrawler 对主社+子社多轮调用 super().get_new_books()，
        计数在同一实例上累积（每轮 mock 返回一本无日期书）"""
        from app.services.publisher_crawler.google_books_publisher import HachetteGoogleCrawler

        crawler = HachetteGoogleCrawler(_make_config())
        crawler._session.get = MagicMock(return_value=_mock_google_response([_volume('No Date', '', '9780000000021')]))

        books = list(crawler.get_new_books(CrawlRequest(max_books=100)).books)

        assert books == []
        # 主社1轮 + 子社5家，每轮至少遍历1本 → 计数跨轮累积不为零
        assert crawler.date_filter_stats['traversed_total'] >= 6
        assert crawler.date_filter_stats['rejected_no_date'] == crawler.date_filter_stats['traversed_total']


class TestMacmillanCounters:
    """Macmillan 两路合并：印记查询与 Sitemap 补充均计入分类"""

    def test_imprint_route_counts_rejections(self):
        crawler = MacmillanCrawler(_make_config())
        items = [
            _volume('Recent', (_today() - timedelta(days=3)).isoformat(), '9780000000031'),
            _volume('No Date', '', '9780000000032'),
        ]
        crawler._session.get = MagicMock(return_value=_mock_google_response(items))

        books = list(crawler._query_imprint('Tor Books', _cutoff(), max_results=10))

        assert [b.title for b in books] == ['Recent']
        assert crawler.date_filter_stats['traversed_total'] == 2
        assert crawler.date_filter_stats['rejected_no_date'] == 1

    def test_sitemap_route_counts_rejections(self):
        from app.services.publisher_crawler.base_crawler import BookInfo

        crawler = MacmillanCrawler(_make_config())
        # 第一路（印记查询）返回空，让流程进入第二路 Sitemap 补充
        crawler._session.get = MagicMock(return_value=_mock_google_response([]))
        crawler._fetch_sitemap_isbns = MagicMock(return_value=['9780000000041', '9780000000042'])  # type: ignore[method-assign]
        crawler._lookup_isbn = MagicMock(  # type: ignore[method-assign]
            side_effect=[
                BookInfo(title='No Date Book', author='A', isbn13='9780000000041', publication_date=None),
                BookInfo(title='Old Book', author='A', isbn13='9780000000042', publication_date=date(2020, 5, 1)),
            ]
        )

        books = list(crawler.get_new_books(CrawlRequest(max_books=10)).books)

        assert books == []
        stats = crawler.date_filter_stats
        assert stats['rejected_no_date'] == 1
        assert stats['rejected_out_of_window'] == 1
