"""主路由辅助函数测试"""

import json
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from app.models.new_book import Publisher
from app.services.book_detail_service import (
    update_book_from_google_books,
)
from app.services.new_book.publisher_manager import PublisherManager
from app.utils.api_helpers import validate_isbn as is_valid_isbn
from app.utils.book_filters import (
    filter_books_by_publisher,
    filter_books_by_search,
    filter_books_by_weeks,
    sort_books,
)
from app.utils.date_helpers import (
    parse_report_content,
    validate_date,
)


@pytest.fixture
def source_isbn_detail(app, monkeypatch):
    """真实详情路由与分类服务，仅替换缓存、上游和详情富化边界。"""
    from app.models.book import Book
    from app.routes import main
    from app.services.book_service import BookService

    category = 'hardcover-fiction'
    monkeypatch.setitem(app.config, 'CATEGORIES', {category: '精装小说'})
    old_raw = {
        'title': 'Cached Selected Book A',
        'author': 'Author A',
        'publisher': 'Publisher A',
        'primary_isbn13': '9780306406157',
        'primary_isbn10': '014312755X',
        'rank': 1,
        'rank_last_week': 2,
        'weeks_on_list': 5,
    }
    new_raw = {
        **old_raw,
        'title': 'New Ranked Book B',
        'author': 'Author B',
        'primary_isbn13': '9781861972712',
        'primary_isbn10': '1861972717',
    }

    def cached_row(raw):
        return Book.from_api_response(raw, category, '精装小说', 'Test List', '2026-10-01', {}).to_dict()

    old_row, new_row = cached_row(old_raw), cached_row(new_raw)
    cache = MagicMock()
    cache.get.return_value = None
    cache.get_stale.return_value = [old_row]
    cache.get_cache_time.return_value = '2026-10-01 00:00:00'
    nyt, google, image = MagicMock(), MagicMock(), MagicMock()
    nyt.fetch_books.return_value = {
        'results': {'books': [new_raw], 'list_name': 'Test List', 'published_date': '2026-10-08'}
    }
    image.get_cached_image_url.return_value = ''
    service = BookService(nyt, google, cache, image, app=app, categories=app.config['CATEGORIES'])
    service._language_pack = MagicMock()
    monkeypatch.setattr(service, '_batch_get_translations', MagicMock(return_value={}))
    monkeypatch.setattr(service, '_batch_get_supplements', MagicMock(return_value={}))
    monkeypatch.setattr(service, '_auto_translate_books', MagicMock())
    monkeypatch.setattr(service, '_notify_data_refreshed', MagicMock())
    get_books = MagicMock(wraps=service.get_books_by_category)
    monkeypatch.setattr(service, 'get_books_by_category', get_books)
    monkeypatch.setattr(main, 'get_service', lambda name: service if name == 'book_service' else None)
    monkeypatch.setattr(main, 'enrich_book_details', MagicMock())
    monkeypatch.setattr(main, 'merge_or_translate_book', MagicMock())
    captured = {}

    def capture(template, **context):
        captured.update(template=template, **context)
        return template

    monkeypatch.setattr(main, 'render_adaptive', capture)
    try:
        yield {
            'client': app.test_client(),
            'service': service,
            'cache': cache,
            'nyt': nyt,
            'get_books': get_books,
            'captured': captured,
            'old_row': old_row,
            'new_row': new_row,
            'category': category,
        }
    finally:
        service._executor.shutdown(wait=True)


class TestBookDetailSourceISBN:
    @pytest.mark.parametrize(
        'source_isbn',
        [
            '9780306406157',
            '978-0-306-40615-7',
            '014312755X',
            '0 143 12755 x',
        ],
    )
    def test_stale_ranking_identity_never_refreshes_to_another_book(self, source_isbn_detail, source_isbn):
        fixture = source_isbn_detail
        response = fixture['client'].get(
            '/book/0',
            query_string={
                'source_isbn': source_isbn,
                'category': fixture['category'],
                'return_to': '/rankings?tab=cross&lang=en',
            },
        )

        assert response.status_code == 200
        assert fixture['captured']['book']['title'] == 'Cached Selected Book A'
        assert fixture['captured']['back_url'] == '/rankings?tab=cross&lang=en'
        fixture['get_books'].assert_called_once_with(fixture['category'], cached_only=True, report_failures=True)
        fixture['nyt'].fetch_books.assert_not_called()

    @pytest.mark.parametrize('old_index', [0, 999])
    def test_reordered_cache_locates_the_isbn_and_updates_actual_index(self, source_isbn_detail, old_index):
        fixture = source_isbn_detail
        fixture['cache'].get.return_value = [fixture['new_row'], fixture['old_row']]
        response = fixture['client'].get(f'/book/{old_index}', query_string={'source_isbn': '9780306406157'})

        assert response.status_code == 200
        assert fixture['captured']['book']['title'] == 'Cached Selected Book A'
        assert fixture['captured']['book_index'] == 1
        fixture['nyt'].fetch_books.assert_not_called()

    @pytest.mark.parametrize(
        'field, cached_isbn, source_isbn',
        [
            ('isbn13', '978-0-306-40615-7', '9780306406157'),
            ('isbn10', '0 143 12755 x', '014312755X'),
        ],
    )
    def test_cached_isbn_formatting_preserves_exact_identity(self, source_isbn_detail, field, cached_isbn, source_isbn):
        fixture = source_isbn_detail
        fixture['cache'].get.return_value = [fixture['new_row'], dict(fixture['old_row'], **{field: cached_isbn})]
        response = fixture['client'].get('/book/0', query_string={'source_isbn': source_isbn})

        assert response.status_code == 200
        assert fixture['captured']['book']['title'] == 'Cached Selected Book A'
        assert fixture['captured']['book_index'] == 1
        fixture['nyt'].fetch_books.assert_not_called()

    def test_removed_isbn_is_404_and_never_falls_back_to_old_index(self, source_isbn_detail):
        fixture = source_isbn_detail
        fixture['cache'].get.return_value = [fixture['new_row']]
        response = fixture['client'].get(
            '/book/0',
            query_string={
                'source_isbn': '9780306406157',
                'return_to': '/rankings?tab=longevity&lang=zh',
            },
        )

        assert response.status_code == 404
        assert fixture['captured']['template'] == 'error.html'
        assert 'book' not in fixture['captured']
        assert fixture['captured']['back_url'] == '/rankings?tab=longevity&lang=zh'
        fixture['nyt'].fetch_books.assert_not_called()

    @pytest.mark.parametrize('cache_state', ['fresh', 'stale'])
    def test_cached_empty_is_404_without_remote_filling(self, source_isbn_detail, cache_state):
        fixture = source_isbn_detail
        fixture['cache'].get.return_value = [] if cache_state == 'fresh' else None
        fixture['cache'].get_stale.return_value = []
        response = fixture['client'].get('/book/0', query_string={'source_isbn': '9780306406157'})

        assert response.status_code == 404
        assert fixture['captured']['template'] == 'error.html'
        fixture['nyt'].fetch_books.assert_not_called()

    @pytest.mark.parametrize('source_isbn', ['', ' ', 'not-an-isbn', '1234567890123', '9780306406157<script>'])
    def test_present_invalid_isbn_is_404_before_category_lookup(self, source_isbn_detail, source_isbn):
        fixture = source_isbn_detail
        response = fixture['client'].get(
            '/book/0',
            query_string={
                'source_isbn': source_isbn,
                'return_to': '/rankings?tab=cross&lang=en',
            },
        )

        assert response.status_code == 404
        assert fixture['captured']['template'] == 'error.html'
        assert fixture['captured']['back_url'] == '/rankings?tab=cross&lang=en'
        assert 'book' not in fixture['captured']
        fixture['get_books'].assert_not_called()
        fixture['nyt'].fetch_books.assert_not_called()

    @pytest.mark.parametrize('mode', ['missing', 'cache_error'])
    def test_cache_failure_retains_500_feedback_instead_of_filling_remote(self, source_isbn_detail, mode):
        from app.utils.exceptions import APIException

        fixture = source_isbn_detail
        if mode == 'missing':
            fixture['cache'].get_stale.return_value = None
        else:
            fixture['cache'].get.side_effect = APIException('Synthetic cache failure')
        response = fixture['client'].get(
            '/book/0',
            query_string={
                'source_isbn': '9780306406157',
                'return_to': '/rankings?tab=cross',
            },
        )

        assert response.status_code == 500
        assert fixture['captured']['template'] == 'error.html'
        assert fixture['captured']['message'] == '榜单暂时无法加载，请稍后再试'
        assert fixture['captured']['back_url'] == '/rankings?tab=cross'
        fixture['get_books'].assert_called_once_with(fixture['category'], cached_only=True, report_failures=True)
        fixture['nyt'].fetch_books.assert_not_called()

    def test_legacy_index_link_preserves_default_refresh_and_safe_return(self, source_isbn_detail):
        fixture = source_isbn_detail
        response = fixture['client'].get('/book/0', query_string={'return_to': 'https://outside.example/rankings'})

        assert response.status_code == 200
        assert fixture['captured']['book']['title'] == 'New Ranked Book B'
        assert fixture['captured']['book_index'] == 0
        assert fixture['captured']['back_url'] == '/'
        fixture['get_books'].assert_called_once_with(fixture['category'])
        fixture['nyt'].fetch_books.assert_called_once_with(fixture['category'], force_refresh=False)


class TestIsValidISBN:
    def test_valid_isbn13(self):
        assert is_valid_isbn('9780743273565') is True

    def test_valid_isbn13_with_dashes(self):
        assert is_valid_isbn('978-0-7432-7356-5') is True

    def test_valid_isbn10(self):
        assert is_valid_isbn('0743273567') is True

    def test_isbn10_with_x(self):
        assert is_valid_isbn('080442957X') is True

    def test_none(self):
        assert is_valid_isbn(None) is False

    def test_empty(self):
        assert is_valid_isbn('') is False

    def test_invalid(self):
        assert is_valid_isbn('not-an-isbn') is False

    def test_isbn13_wrong_prefix(self):
        assert is_valid_isbn('9770743273565') is False


class TestFilterBooksBySearch:
    def test_no_query(self):
        books = [{'title': 'Book A', 'author': 'Author A'}]
        assert filter_books_by_search(books, '') == books

    def test_none_query(self):
        books = [{'title': 'Book A', 'author': 'Author A'}]
        assert filter_books_by_search(books, None) == books

    def test_empty_books(self):
        assert filter_books_by_search([], 'test') == []

    def test_match_title(self):
        books = [
            {'title': 'Python Programming', 'author': 'Author A'},
            {'title': 'Java Guide', 'author': 'Author B'},
        ]
        result = filter_books_by_search(books, 'python')
        assert len(result) == 1
        assert result[0]['title'] == 'Python Programming'

    def test_match_author(self):
        books = [
            {'title': 'Book A', 'author': 'John Smith'},
            {'title': 'Book B', 'author': 'Jane Doe'},
        ]
        result = filter_books_by_search(books, 'john')
        assert len(result) == 1
        assert result[0]['author'] == 'John Smith'

    def test_case_insensitive(self):
        books = [{'title': 'PYTHON', 'author': 'Author'}]
        result = filter_books_by_search(books, 'python')
        assert len(result) == 1


class TestFilterBooksByPublisher:
    def test_no_publisher(self):
        books = [{'publisher': 'Penguin'}]
        assert filter_books_by_publisher(books, '') == books

    def test_match_publisher(self):
        books = [
            {'publisher': 'Penguin Random House'},
            {'publisher': 'HarperCollins'},
        ]
        result = filter_books_by_publisher(books, 'penguin')
        assert len(result) == 1

    def test_empty_books(self):
        assert filter_books_by_publisher([], 'Penguin') == []


class TestFilterBooksByWeeks:
    def test_new_books(self):
        books = [
            {'weeks_on_list': 1},
            {'weeks_on_list': 5},
        ]
        result = filter_books_by_weeks(books, 'new')
        assert len(result) == 1
        assert result[0]['weeks_on_list'] == 1

    def test_trending_books(self):
        books = [
            {'weeks_on_list': 1},
            {'weeks_on_list': 3},
            {'weeks_on_list': 10},
        ]
        result = filter_books_by_weeks(books, 'trending')
        assert len(result) == 1
        assert result[0]['weeks_on_list'] == 3

    def test_classic_books(self):
        books = [
            {'weeks_on_list': 3},
            {'weeks_on_list': 10},
        ]
        result = filter_books_by_weeks(books, 'classic')
        assert len(result) == 1
        assert result[0]['weeks_on_list'] == 10

    def test_no_filter(self):
        books = [{'weeks_on_list': 1}]
        assert filter_books_by_weeks(books, '') == books

    def test_unknown_filter(self):
        books = [{'weeks_on_list': 1}]
        assert filter_books_by_weeks(books, 'unknown') == books


class TestSortBooks:
    def test_empty_books(self):
        assert sort_books([], 'rank_change') == []

    def test_sort_by_rank_change(self):
        books = [
            {'rank': 1, 'rank_last_week': '5'},
            {'rank': 3, 'rank_last_week': '3'},
            {'rank': 2, 'rank_last_week': '10'},
        ]
        result = sort_books(books, 'rank_change')
        assert result[0]['rank'] == 2

    def test_sort_by_weeks_desc(self):
        books = [
            {'weeks_on_list': 2},
            {'weeks_on_list': 10},
            {'weeks_on_list': 5},
        ]
        result = sort_books(books, 'weeks_desc')
        assert result[0]['weeks_on_list'] == 10

    def test_sort_by_weeks_asc(self):
        books = [
            {'weeks_on_list': 10},
            {'weeks_on_list': 2},
        ]
        result = sort_books(books, 'weeks_asc')
        assert result[0]['weeks_on_list'] == 2

    def test_no_sort(self):
        books = [{'rank': 5}, {'rank': 1}]
        assert sort_books(books, '') == books

    def test_rank_change_with_none_last_week(self):
        books = [
            {'rank': 1, 'rank_last_week': None},
            {'rank': 2, 'rank_last_week': '5'},
        ]
        result = sort_books(books, 'rank_change')
        assert len(result) == 2


class TestValidateDate:
    def test_valid_date(self):
        is_valid, error, date_obj = validate_date('2024-01-15')
        assert is_valid is True
        assert error is None
        assert date_obj is not None

    def test_invalid_format(self):
        is_valid, _error, date_obj = validate_date('2024/01/15')
        assert is_valid is False
        assert date_obj is None

    def test_too_old(self):
        is_valid, _error, _date_obj = validate_date('2019-01-01')
        assert is_valid is False

    def test_future_date(self):
        is_valid, _error, _date_obj = validate_date('2099-01-01')
        assert is_valid is False

    def test_empty(self):
        is_valid, _error, _date_obj = validate_date('')
        assert is_valid is False

    def test_none(self):
        is_valid, _error, _date_obj = validate_date(None)
        assert is_valid is False

    def test_wrong_length(self):
        is_valid, _error, _date_obj = validate_date('2024-1-5')
        assert is_valid is False


class TestParseReportContent:
    def test_valid_json(self):
        report = MagicMock()
        report.content = json.dumps({'key': 'value'})
        result = parse_report_content(report)
        assert result == {'key': 'value'}

    def test_dict_content(self):
        report = MagicMock()
        report.content = {'key': 'value'}
        result = parse_report_content(report)
        assert result == {'key': 'value'}

    def test_none_report(self):
        assert parse_report_content(None) is None

    def test_none_content(self):
        report = MagicMock()
        report.content = None
        assert parse_report_content(report) is None

    def test_invalid_json(self):
        report = MagicMock()
        report.content = 'not json{'
        assert parse_report_content(report) is None


class TestUpdateBookFromGoogleBooks:
    def test_updates_details(self):
        book = {}
        details = {'details': 'A great book description'}
        with patch('app.services.book_detail_service.translate_field_async'):
            update_book_from_google_books(book, details)
        assert book['details'] == 'A great book description'

    def test_skips_no_description(self):
        book = {}
        details = {'details': 'No detailed description available.'}
        update_book_from_google_books(book, details)
        assert 'details' not in book

    def test_updates_page_count(self):
        book = {}
        details = {'page_count': 320}
        update_book_from_google_books(book, details)
        assert book['page_count'] == '320'

    def test_skips_unknown_page_count(self):
        book = {}
        details = {'page_count': 'Unknown'}
        update_book_from_google_books(book, details)
        assert 'page_count' not in book

    def test_updates_publisher_when_unknown(self):
        book = {'publisher': 'Unknown'}
        details = {'publisher': 'Penguin'}
        update_book_from_google_books(book, details)
        assert book['publisher'] == 'Penguin'

    def test_keeps_existing_publisher(self):
        book = {'publisher': 'Scribner'}
        details = {'publisher': 'Penguin'}
        update_book_from_google_books(book, details)
        assert book['publisher'] == 'Scribner'

    def test_updates_cover_url(self):
        book = {}
        details = {'cover_url': 'https://example.com/cover.jpg'}
        update_book_from_google_books(book, details)
        assert book['cover'] == 'https://example.com/cover.jpg'

    def test_does_not_overwrite_cover(self):
        book = {'cover': 'existing.jpg'}
        details = {'cover_url': 'new.jpg'}
        update_book_from_google_books(book, details)
        assert book['cover'] == 'existing.jpg'

    def test_updates_isbn13(self):
        book = {}
        details = {'isbn_13': '9780743273565'}
        update_book_from_google_books(book, details)
        assert book['isbn13'] == '9780743273565'

    def test_updates_publication_dt(self):
        book = {}
        details = {'publication_dt': '2024-01-15'}
        update_book_from_google_books(book, details)
        assert book['publication_dt'] == '2024-01-15'

    def test_updates_language(self):
        book = {}
        details = {'language': 'English'}
        update_book_from_google_books(book, details)
        assert book['language'] == 'English'


class TestMainRoutes:
    def test_index_page(self, client):
        response = client.get('/')
        assert response.status_code == 200

    def test_index_with_category(self, client):
        response = client.get('/?category=hardcover-fiction')
        assert response.status_code == 200

    def test_index_with_search(self, client):
        response = client.get('/?search=python')
        assert response.status_code == 200

    def test_index_with_view_grid(self, client):
        response = client.get('/?view=grid')
        assert response.status_code == 200

    def test_index_with_invalid_view(self, client):
        response = client.get('/?view=invalid')
        assert response.status_code == 200

    def test_index_with_publisher_filter(self, client):
        response = client.get('/?publisher=Penguin')
        assert response.status_code == 200

    def test_index_with_weeks_filter(self, client):
        response = client.get('/?weeks=new')
        assert response.status_code == 200

    def test_index_with_sort(self, client):
        response = client.get('/?sort=rank_change')
        assert response.status_code == 200

    def test_favicon(self, client):
        response = client.get('/favicon.ico')
        assert response.status_code in (200, 404)

    def test_about_page(self, client):
        response = client.get('/about')
        assert response.status_code == 200

    def test_publishers_page(self, client):
        response = client.get('/publishers')
        assert response.status_code == 200

    @patch('app.routes.main.get_new_book_modules')
    def test_publishers_page_links_matched_directory_entry_to_new_books(self, mock_get_modules, client):
        """静态目录里 name_en 能直接匹配数据库出版社的条目（如 Penguin Random House），应出现指向新书速递的链接"""
        mock_pub = MagicMock()
        mock_pub.id = 42
        mock_pub.name_en = 'Penguin Random House'
        mock_modules = MagicMock()
        mock_modules.publisher_manager.get_publishers.return_value = [mock_pub]
        mock_get_modules.return_value = mock_modules

        response = client.get('/publishers')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert f'/new-books?publisher={mock_pub.id}' in html

    @patch('app.routes.main.get_new_book_modules')
    def test_publishers_page_links_aliased_directory_entry_to_new_books(self, mock_get_modules, client):
        """静态目录里的「Hachette Book Group」应通过别名映射链接到数据库里的「Hachette」"""
        mock_pub = MagicMock()
        mock_pub.id = 7
        mock_pub.name_en = 'Hachette'
        mock_modules = MagicMock()
        mock_modules.publisher_manager.get_publishers.return_value = [mock_pub]
        mock_get_modules.return_value = mock_modules

        response = client.get('/publishers')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert f'/new-books?publisher={mock_pub.id}' in html

    @patch('app.routes.main.get_new_book_modules')
    def test_publishers_page_no_link_for_unmatched_directory_entry(self, mock_get_modules, client):
        """数据库里没有对应记录的目录条目（如大多数小型出版社）不应出现「查看新书」链接"""
        mock_modules = MagicMock()
        mock_modules.publisher_manager.get_publishers.return_value = []
        mock_get_modules.return_value = mock_modules

        response = client.get('/publishers')
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert '/new-books?publisher=' not in html

    @patch('app.routes.main.get_new_book_modules')
    def test_publishers_page_degrades_when_new_book_service_fails(self, mock_get_modules, client):
        """新书服务查询失败时,出版社目录页仍应正常渲染（只是不显示跳转链接）"""
        mock_modules = MagicMock()
        mock_modules.publisher_manager.get_publishers.side_effect = Exception('DB error')
        mock_get_modules.return_value = mock_modules

        response = client.get('/publishers')
        assert response.status_code == 200

    def test_cache_management_page(self, client):
        response = client.get('/cache-management')
        assert response.status_code == 200

    def test_analytics_dashboard_page(self, client):
        response = client.get('/analytics')
        assert response.status_code == 200

    def test_set_language_en(self, client):
        response = client.get('/set-language?lang=en&next=/')
        assert response.status_code == 302

    def test_set_language_zh(self, client):
        response = client.get('/set-language?lang=zh&next=/')
        assert response.status_code == 302

    def test_set_language_invalid(self, client):
        response = client.get('/set-language?lang=fr&next=/')
        assert response.status_code == 302

    def test_set_language_unsafe_redirect(self, client):
        response = client.get('/set-language?lang=en&next=https://evil.com')
        assert response.status_code == 302

    def test_set_language_ip_host_omits_cookie_domain(self, client):
        response = client.get('/set-language?lang=en&next=/', headers={'Host': '192.168.1.23:5000'})
        cookie = response.headers.get('Set-Cookie', '')
        assert 'Domain=' not in cookie

    def test_set_language_domain_host_sets_cookie_domain(self, client):
        response = client.get('/set-language?lang=en&next=/', headers={'Host': 'example.com'})
        cookie = response.headers.get('Set-Cookie', '')
        assert 'Domain=example.com' in cookie

    def test_cached_image_invalid_filename(self, client):
        response = client.get('/cache/images/../../../etc/passwd')
        assert response.status_code == 404

    def test_cached_image_invalid_format(self, client):
        response = client.get('/cache/images/test.png')
        assert response.status_code == 404

    def test_book_details_api_missing_params(self, client):
        response = client.get('/api/book-details')
        json.loads(response.data)
        assert response.status_code == 400

    def test_api_category_books(self, client):
        response = client.get('/api/category-books?category=hardcover-fiction')
        assert response.status_code == 200

    def test_api_category_books_invalid(self, client):
        response = client.get('/api/category-books?category=invalid')
        assert response.status_code == 400

    def test_weekly_reports_page(self, client):
        response = client.get('/reports/weekly')
        assert response.status_code == 200

    def test_weekly_report_detail_invalid_date(self, client):
        response = client.get('/reports/weekly/invalid-date')
        assert response.status_code == 200

    def test_weekly_report_detail_future_date(self, client):
        response = client.get('/reports/weekly/2099-01-01')
        assert response.status_code == 200

    def test_new_books_page(self, client):
        response = client.get('/new-books')
        assert response.status_code == 200

    def test_awards_page(self, client):
        response = client.get('/awards')
        assert response.status_code == 200

    def test_book_detail_invalid_index(self, client):
        from unittest.mock import patch

        with patch('app.routes.main._get_books_for_category', return_value=([], None)):
            response = client.get('/book/99999')
        assert response.status_code == 404

    def test_book_detail_negative_index(self, client):
        response = client.get('/book/-1')
        assert response.status_code in (200, 404)


def _capture_about_render(monkeypatch):
    captured = {}

    def _render(template, **kwargs):
        captured['template'] = template
        captured['kwargs'] = kwargs
        return 'ok'

    monkeypatch.setattr('app.routes.main.render_adaptive', _render)
    return captured


def _use_real_publisher_manager(monkeypatch):
    monkeypatch.setattr(
        'app.routes.main.get_new_book_modules',
        lambda: SimpleNamespace(publisher_manager=PublisherManager()),
    )


class TestAboutStats:
    def test_about_stats_partition_active_rows_one_query(self, app, db, monkeypatch):
        monkeypatch.setitem(
            app.config,
            'CATEGORIES',
            {'hardcover-fiction': {}, 'hardcover-nonfiction': {}, 'advice': {}},
        )
        assert 'memory' in str(db.engine.url)
        db.session.query(Publisher).delete()
        db.session.commit()
        db.session.add_all(
            [
                Publisher(
                    name='谷歌图书出版社',
                    name_en='Google Books',
                    crawler_class='PrhApiCrawler',
                    is_active=True,
                ),
                Publisher(
                    name='哈珀柯林斯',
                    name_en='HarperCollins',
                    crawler_class='HarperCollinsGoogleCrawler',
                    is_active=True,
                ),
                Publisher(
                    name='综合来源甲',
                    name_en='Renamed Books Aggregator',
                    crawler_class='GoogleBooksCrawler',
                    is_active=True,
                ),
                Publisher(
                    name='综合来源乙',
                    name_en='Renamed Library Aggregator',
                    crawler_class='OpenLibraryCrawler',
                    is_active=True,
                ),
                Publisher(
                    name='休眠出版社',
                    name_en='Inactive House',
                    crawler_class='SnsApiCrawler',
                    is_active=False,
                ),
                Publisher(
                    name='休眠来源',
                    name_en='Inactive Source',
                    crawler_class='GoogleBooksCrawler',
                    is_active=False,
                ),
            ]
        )
        db.session.commit()
        _use_real_publisher_manager(monkeypatch)
        captured = _capture_about_render(monkeypatch)
        selects = []

        def _count_publisher_selects(conn, cursor, statement, parameters, context, executemany):
            normalized = statement.lower()
            if normalized.lstrip().startswith('select') and 'publishers' in normalized:
                selects.append(statement)

        event.listen(Engine, 'before_cursor_execute', _count_publisher_selects)
        try:
            response = app.test_client().get('/about')
        finally:
            event.remove(Engine, 'before_cursor_execute', _count_publisher_selects)

        assert response.status_code == 200
        assert captured['template'] == 'about.html'
        assert captured['kwargs']['about_stats'] == {
            'nyt_category_count': 3,
            'publisher_count': 2,
            'source_count': 2,
        }
        assert len(selects) == 1

    def test_about_stats_empty_categories_and_publishers(self, app, db, monkeypatch):
        monkeypatch.setitem(app.config, 'CATEGORIES', {})
        _use_real_publisher_manager(monkeypatch)
        captured = _capture_about_render(monkeypatch)

        response = app.test_client().get('/about')

        assert response.status_code == 200
        assert captured['kwargs']['about_stats'] == {
            'nyt_category_count': 0,
            'publisher_count': 0,
            'source_count': 0,
        }

    def test_about_stats_provider_failure_marks_counts_unavailable(self, app, db, monkeypatch):
        monkeypatch.setitem(
            app.config,
            'CATEGORIES',
            {'one': {}, 'two': {}, 'three': {}},
        )

        def _boom():
            raise RuntimeError('publisher modules unavailable')

        monkeypatch.setattr('app.routes.main.get_new_book_modules', _boom)
        captured = _capture_about_render(monkeypatch)

        response = app.test_client().get('/about')

        assert response.status_code == 200
        assert captured['kwargs']['about_stats'] == {
            'nyt_category_count': 3,
            'publisher_count': None,
            'source_count': None,
        }

    _DETAIL_SPECS = (
        ('book', '/book/0', '/', 'book_detail.html'),
        ('award', '/award-book/1', '/awards', 'award_book_detail.html'),
        ('new', '/new-book/1', '/new-books', 'new_book_detail.html'),
    )

    def _arm_detail(self, monkeypatch, route, mode):
        from sqlalchemy.exc import SQLAlchemyError

        box = {}

        def _render(template, **context):
            box['template'] = template
            box['context'] = context
            return 'captured'

        monkeypatch.setattr('app.routes.main.render_adaptive', _render)

        def _fail_or(book):
            if mode == 'failure':
                raise SQLAlchemyError('db down')
            return None if mode == 'missing' else book

        if route == 'book':

            def _books(_category):
                if mode == 'failure':
                    from app.utils import ExternalAPIError

                    raise ExternalAPIError(api_name='nyt', message='unavailable')
                row = {'title': 'NYT Title', 'author': 'NYT Author', 'isbn13': ''}
                return ([] if mode == 'missing' else [row]), None

            monkeypatch.setattr('app.routes.main._get_books_for_category', _books)
        elif route == 'award':
            from app.models.schemas import AwardBook

            book = AwardBook(
                award_id=1,
                year=2024,
                title='Award Title',
                author='Award Author',
                title_zh='获奖书名',
                description='Award description',
                description_zh='获奖简介',
                is_displayable=True,
            )
            monkeypatch.setattr(
                'app.services.award_book_service.AwardBookService.get_award_book_by_id',
                lambda _self, _book_id: _fail_or(book),
            )
            rec = MagicMock()
            rec.get_similarity_recommendations.return_value = {'recommendations': []}
            monkeypatch.setattr('app.routes.main.get_or_create_recommendation_service', lambda: rec)
        else:
            from app.models.new_book import NewBook

            book = NewBook(
                publisher_id=1,
                title='New Title',
                author='New Author',
                title_zh='新书书名',
                description='New description',
                description_zh='新书简介',
            )
            monkeypatch.setattr(
                'app.routes.main.get_new_book_modules',
                lambda: SimpleNamespace(query_service=SimpleNamespace(get_book=lambda _id: _fail_or(book))),
            )
        return box

    def test_detail_primary_load_status_and_fallback(self, app, db, monkeypatch):
        expect = {'ok': 200, 'missing': 404, 'failure': 500}
        for route, path, fallback, ok_template in self._DETAIL_SPECS:
            for mode, status in expect.items():
                box = self._arm_detail(monkeypatch, route, mode)
                response = app.test_client().get(path, headers={'Referer': 'https://evil.example/ignored'})
                assert response.status_code == status
                assert box['template'] == (ok_template if mode == 'ok' else 'error.html')
                assert box['context']['back_url'] == fallback
        assert db is not None

    def test_detail_return_to_safe_query_ignores_referrer(self, app, db, monkeypatch):
        safe = '/new-books?search=https%3A%2F%2Fexample.com&lang=en&view=list&page=2'
        values = (
            safe,
            'https://evil.example/phish',
            '//evil.example/phish',
            '/\\evil.example',
            '/ok\n',
            '/%2F%2Fevil.example',
            '/%252F%252Fevil.example',
            None,
        )
        for route, path, fallback, ok_template in self._DETAIL_SPECS:
            for value in values:
                box = self._arm_detail(monkeypatch, route, 'ok')
                query = {} if value is None else {'return_to': value}
                response = app.test_client().get(
                    path,
                    query_string=query,
                    headers={'Referer': 'https://evil.example/ignored'},
                )
                assert response.status_code == 200
                assert box['template'] == ok_template
                assert box['context']['back_url'] == (safe if value == safe else fallback)
        assert db is not None
