"""UX 搜索回归测试（audit item01：可见中文书名可搜索）。

覆盖：
- filter_books_by_search 中文书名 / 英文书名 / 作者 / author_zh 检索，空值不崩溃
- 跨分类搜索的 source_category / source_index 标注保留
- 首页搜索的 search_status / search_unavailable_count / data_load_failed 契约：
  全部抓取失败 / 部分失败 / 成功但零结果 / 正常，互不误判
- 搜索路径不触发翻译（auto_translate=False, notify_refresh=False）
"""

from unittest.mock import Mock, patch

import pytest

from app.routes import main as main_routes
from app.services.book_service import BookService
from app.utils import ExternalAPIError
from app.utils.book_filters import filter_books_by_search
from app.utils.exceptions import APIException

# ---------------------------------------------------------------- 过滤单元测试


class TestFilterBooksBySearch:
    def test_matches_chinese_title_zh(self):
        books = [
            {'title': 'The Great Gatsby', 'title_zh': '了不起的盖茨比', 'author': 'F. Scott Fitzgerald'},
            {'title': 'Other Book', 'author': 'X'},
        ]
        result = filter_books_by_search(books, '了不起')
        assert len(result) == 1
        assert result[0]['title'] == 'The Great Gatsby'

    def test_taipei_and_full_title_match(self):
        books = [{'title': 'Tales of Taipei', 'title_zh': '台北故事', 'author': 'X'}]
        assert len(filter_books_by_search(books, '台北')) == 1
        assert len(filter_books_by_search(books, '台北故事')) == 1

    def test_english_title_case_insensitive(self):
        books = [{'title': 'PYTHON Programming', 'author': 'A'}]
        assert len(filter_books_by_search(books, 'python')) == 1
        assert len(filter_books_by_search(books, 'PROGRAMMING')) == 1

    def test_author_case_insensitive(self):
        books = [{'title': 'X', 'author': 'John Smith'}, {'title': 'Y', 'author': 'Jane Doe'}]
        assert len(filter_books_by_search(books, 'JOHN')) == 1
        assert len(filter_books_by_search(books, 'john smith')) == 1

    def test_author_zh_if_stored(self):
        books = [{'title': 'Harry Potter', 'author': 'J.K. Rowling', 'author_zh': 'J·K·罗琳'}]
        assert len(filter_books_by_search(books, '罗琳')) == 1

    def test_none_title_author_does_not_crash(self):
        books = [
            {'title': None, 'title_zh': None, 'author': None},
            {'title': 'Real Book', 'author': 'B'},
        ]
        result = filter_books_by_search(books, 'real')
        assert len(result) == 1
        assert result[0]['title'] == 'Real Book'

    def test_none_fields_no_match_returns_empty(self):
        books = [{'title': None, 'title_zh': None, 'author': None}]
        assert filter_books_by_search(books, 'something') == []

    def test_empty_query_keeps_all(self):
        books = [{'title': 'A', 'author': 'B'}, {'title': 'C', 'author': 'D'}]
        assert filter_books_by_search(books, '') == books
        assert filter_books_by_search(books, '   ') == books

    def test_none_query_keeps_all(self):
        books = [{'title': 'A', 'author': 'B'}]
        assert filter_books_by_search(books, None) == books

    def test_empty_books(self):
        assert filter_books_by_search([], 'python') == []

    def test_whitespace_query_is_trimmed(self):
        books = [{'title': '台北故事', 'author': 'X'}]
        assert len(filter_books_by_search(books, '  台北  ')) == 1


# --------------------------------------------------------- 来源标注与翻译开关


def _make_book(title, author, rank=None):
    book = {'title': title, 'author': author}
    if rank is not None:
        book['rank'] = rank
    return book


class TestSearchAllCategories:
    def test_source_category_and_index_preserved_with_rank(self):
        by_cat = {
            'hardcover-fiction': [_make_book('A', 'X', rank=3)],
            'business-books': [_make_book('B', 'Y', rank=1)],
        }
        with patch.object(main_routes, '_fetch_all_category_books_with_status', return_value=(by_cat, [])):
            merged, unavailable = main_routes._search_all_categories('q', {})
        assert unavailable == []
        assert len(merged) == 2
        assert merged[0]['source_category'] == 'hardcover-fiction'
        assert merged[0]['source_index'] == 2  # rank 3 -> index 2
        assert merged[1]['source_category'] == 'business-books'
        assert merged[1]['source_index'] == 0  # rank 1 -> index 0

    def test_source_index_falls_back_to_position_when_rank_missing(self):
        by_cat = {'hardcover-fiction': [_make_book('A', 'X'), _make_book('B', 'Y')]}
        with patch.object(main_routes, '_fetch_all_category_books_with_status', return_value=(by_cat, [])):
            merged, _ = main_routes._search_all_categories('q', {})
        assert merged[0]['source_index'] == 0
        assert merged[1]['source_index'] == 1

    def test_does_not_annotate_unavailable_categories(self):
        by_cat = {'hardcover-fiction': [_make_book('A', 'X', rank=1)]}
        with patch.object(
            main_routes, '_fetch_all_category_books_with_status', return_value=(by_cat, ['business-books'])
        ):
            merged, unavailable = main_routes._search_all_categories('q', {})
        assert unavailable == ['business-books']
        assert len(merged) == 1
        assert merged[0]['source_category'] == 'hardcover-fiction'


class TestFetchAllCategoryBooksWithStatus:
    def test_failed_categories_counted_as_unavailable_not_empty(self):
        """成功但空、失败两种情况要分开：空不算失败。"""
        categories = {'a': 'A', 'b': 'B'}
        with patch.object(
            main_routes,
            '_get_books_for_category',
            side_effect=[
                ([], None),  # a 成功但空 -> 不算失败
                ExternalAPIError('boom'),  # b 失败
            ],
        ):
            books, unavailable = main_routes._fetch_all_category_books_with_status(categories)
        assert books == {'a': []}
        assert unavailable == ['b']

    def test_no_paid_translation_on_search(self):
        """搜索抓取路径必须关闭翻译与刷新通知（auto_translate=False, notify_refresh=False），
        并开启显式失败上报（report_failures=True）以区分真实失败与空结果。"""
        categories = {'a': 'A', 'b': 'B'}
        with patch.object(main_routes, '_get_books_for_category', return_value=([], None)) as mock_get:
            main_routes._fetch_all_category_books_with_status(categories)
        for call in mock_get.call_args_list:
            _args, kwargs = call
            assert kwargs.get('auto_translate') is False
            assert kwargs.get('notify_refresh') is False
            assert kwargs.get('report_failures') is True


# ---------------------------------------------------------------- 首页路由契约


class TestIndexSearchStatus:
    def _get_index_context(self, client, search='台北'):
        captured = {}

        def fake_render(template_name, **context):
            captured.update(context)
            return 'rendered'

        with patch.object(main_routes, 'render_adaptive', side_effect=fake_render):
            url = f'/?search={search}' if search else '/'
            client.get(url)
        return captured

    def test_ready_status_with_results(self, client):
        books = [{'title': '台北故事', 'author': 'X'}]
        with patch.object(main_routes, '_search_all_categories', return_value=(books, [])) as mock_search:
            ctx = self._get_index_context(client)
        mock_search.assert_called_once()
        assert ctx['search_status'] == 'ready'
        assert ctx['search_unavailable_count'] == 0
        assert ctx['data_load_failed'] is False

    def test_empty_status_when_no_category_failed(self, client):
        # 全部抓取成功，但搜索零匹配 -> 真实零结果，不是失败
        with patch.object(main_routes, '_search_all_categories', return_value=([], [])):
            ctx = self._get_index_context(client, search='不存在关键词')
        assert ctx['search_status'] == 'empty'
        assert ctx['search_unavailable_count'] == 0

    def test_partial_status_when_some_categories_failed(self, client):
        books = [{'title': '台北故事', 'author': 'X'}]
        with patch.object(main_routes, '_search_all_categories', return_value=(books, ['business-books'])):
            ctx = self._get_index_context(client)
        assert ctx['search_status'] == 'partial'
        assert ctx['search_unavailable_count'] == 1

    def test_failed_status_when_all_categories_failed(self, client, app):
        # 需要 unavailable 覆盖全部 13 个分类 -> search_status=failed
        total = len(app.config['CATEGORIES'])
        with patch.object(
            main_routes,
            '_search_all_categories',
            return_value=([], list(app.config['CATEGORIES'].keys())),
        ):
            ctx = self._get_index_context(client)
        assert ctx['search_status'] == 'failed'
        assert ctx['search_unavailable_count'] == total

    def test_data_load_failed_only_on_non_search(self, client, app):
        # 无搜索词，单分类抓取抛异常 -> data_load_failed=True，search_status=ready
        from app.utils import ExternalAPIError as Exc

        with patch.object(main_routes, '_get_books_for_category', side_effect=Exc('boom')):
            ctx = self._get_index_context(client, search='')
        assert ctx['data_load_failed'] is True
        assert ctx['search_status'] == 'ready'
        assert ctx['search_unavailable_count'] == 0

    def test_data_load_failed_false_when_search(self, client):
        with patch.object(main_routes, '_search_all_categories', return_value=([], [])):
            ctx = self._get_index_context(client, search='台北')
        assert ctx['data_load_failed'] is False


# ----------------------------------------- 真实 BookService 失败传播（route 契约）


def _build_book_service(nyt_client, language_pack_path=None):
    """构造一个真实 BookService，仅 NYT 依赖被替换为 Mock，其余依赖为惰性 Mock。

    显式传入 language_pack_path 以避免从 Mock app 解析 static_folder。
    """
    return BookService(
        nyt_client=nyt_client,
        google_client=Mock(),
        cache_service=Mock(),
        image_cache=Mock(),
        app=None,
        categories={'hardcover-fiction': '精装小说', 'business-books': '商业'},
        language_pack_path=language_pack_path,
    )


class TestRealFailurePropagation:
    """用真实 BookService 驱动 route 包装，验证失败会被真正上抛而非伪装成空。"""

    @pytest.fixture
    def real_service(self):
        """构造一个真实 BookService（NYT 依赖由测试提供），其余依赖为惰性 Mock。"""

        def _register(nyt_client):
            return _build_book_service(nyt_client)

        return _register

    def test_get_books_for_category_propagates_report_failures(self, app, real_service):
        """真实 BookService：API 抛异常且无过期缓存，report_failures=True 必须上抛 ExternalAPIError。"""
        nyt = Mock()
        nyt.fetch_books.side_effect = APIException('NYT down')
        svc = real_service(nyt)
        svc._cache.get.return_value = None
        svc._cache.get_stale.return_value = None

        with app.app_context():
            app.extensions['book_service'] = svc
            try:
                with pytest.raises(ExternalAPIError):
                    main_routes._get_books_for_category('hardcover-fiction', report_failures=True)
            finally:
                app.extensions.pop('book_service', None)

    def test_get_books_for_category_genuine_empty_stays_empty(self, app, real_service):
        """真实 BookService：成功但空，report_failures=True 仍返回空列表而非抛异常。"""
        nyt = Mock()
        nyt.fetch_books.return_value = {
            'results': {'books': [], 'list_name': 'Hardcover Fiction', 'published_date': '2026-09-06'}
        }
        svc = real_service(nyt)
        svc._cache.get.return_value = None
        svc._cache.get_stale.return_value = None

        with app.app_context():
            app.extensions['book_service'] = svc
            try:
                books, _ = main_routes._get_books_for_category('hardcover-fiction', report_failures=True)
                assert books == []
            finally:
                app.extensions.pop('book_service', None)

    def test_missing_service_signaled_unavailable_for_homepage(self, app):
        """无 book_service 且 report_failures=True 时，必须上抛 ExternalAPIError 而非返回 ([], None)。"""
        with app.app_context():
            app.extensions.pop('book_service', None)
            with pytest.raises(ExternalAPIError):
                main_routes._get_books_for_category('hardcover-fiction', report_failures=True)

    def test_missing_service_without_report_keeps_old_behavior(self, app):
        """无 book_service 且未要求上报时，维持旧行为返回 ([], None)。"""
        with app.app_context():
            app.extensions.pop('book_service', None)
            books, update_time = main_routes._get_books_for_category('hardcover-fiction')
            assert books == []
            assert update_time is None

    def test_search_counts_real_failure_as_unavailable(self, app, real_service):
        """真实 BookService：一个分类真实失败记入 unavailable，成功但空不算失败。"""
        nyt = Mock()

        def _fetch(category, force_refresh=False):
            if category == 'hardcover-fiction':
                raise APIException('NYT down')
            return {'results': {'books': [], 'list_name': 'Business', 'published_date': '2026-09-06'}}

        nyt.fetch_books.side_effect = _fetch
        svc = real_service(nyt)
        svc._cache.get.return_value = None
        svc._cache.get_stale.return_value = None

        categories = {'hardcover-fiction': '精装小说', 'business-books': '商业'}
        with app.app_context():
            app.extensions['book_service'] = svc
            try:
                books, unavailable = main_routes._fetch_all_category_books_with_status(categories)
            finally:
                app.extensions.pop('book_service', None)

        assert unavailable == ['hardcover-fiction']
        assert books == {'business-books': []}
