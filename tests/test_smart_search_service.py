"""
智能搜索服务单元测试

覆盖范围：
- SmartSearchService.search（空关键词、分页、年份/奖项筛选、异常）
- _sanitize_keyword（空值、特殊字符、长度截断）
- _apply_award_search_conditions / _apply_new_book_search_conditions
- _format_book / _format_new_book
- _empty_search_result
- _generate_suggestions（历史搜索、热门搜索、异常）
- get_suggestions（前缀搜索、去重、异常）
- get_popular_searches（正常/异常）
- save_search_history（正常/异常/空关键词）
- get_search_history（正常/异常/去重）
- clear_search_history（正常/异常）
"""

from datetime import UTC, datetime
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import text

from app.services.smart_search_service import SmartSearchService


@pytest.fixture
def service():
    return SmartSearchService(categories={'fiction': '小说'})


def _make_flask_query(results=None, count_val=0):
    """创建模拟 Flask-SQLAlchemy 查询链的 Mock"""
    q = Mock()
    q.filter.return_value = q
    q.count.return_value = count_val
    q.order_by.return_value = q
    q.offset.return_value = q
    q.limit.return_value = q
    q.all.return_value = results or []
    q.with_entities.return_value = q
    q.distinct.return_value = q
    q.group_by.return_value = q
    return q


class TestSanitizeKeyword:
    def test_empty_string(self, service):
        assert service._sanitize_keyword('') == ''

    def test_none_returns_empty(self, service):
        assert service._sanitize_keyword(None) == ''

    def test_strips_whitespace(self, service):
        assert service._sanitize_keyword('  hello  ') == 'hello'

    def test_removes_special_characters(self, service):
        result = service._sanitize_keyword('hello@#$%^&*()')
        assert result == 'hello'

    def test_preserves_chinese_characters(self, service):
        result = service._sanitize_keyword('中文搜索')
        assert result == '中文搜索'

    def test_preserves_hyphen(self, service):
        result = service._sanitize_keyword('self-help')
        assert result == 'self-help'

    def test_compresses_multiple_spaces(self, service):
        result = service._sanitize_keyword('hello   world')
        assert result == 'hello world'

    def test_truncates_at_100_chars(self, service):
        long_keyword = 'a' * 150
        result = service._sanitize_keyword(long_keyword)
        assert len(result) == 100


class TestEmptySearchResult:
    def test_returns_correct_structure(self, service):
        result = service._empty_search_result()
        assert result['results'] == []
        assert result['total'] == 0
        assert result['keyword'] == ''
        assert result['search_type'] == 'all'
        assert result['suggestions'] == []
        assert result['pagination']['limit'] == 20
        assert result['pagination']['offset'] == 0
        assert result['pagination']['has_more'] is False


class TestFormatBook:
    def test_formats_book_with_award(self, service):
        mock_book = Mock()
        mock_book.id = 1
        mock_book.title = 'Test Title'
        mock_book.title_zh = '测试标题'
        mock_book.author = 'Author'
        mock_book.publisher = 'Publisher'
        mock_book.year = 2024
        mock_book.category = 'Fiction'
        mock_book.rank = 1
        mock_book.cover_original_url = 'http://example.com/cover.jpg'
        mock_book.isbn13 = '9781234567890'
        mock_book.award_id = 10
        mock_award = Mock()
        mock_award.id = 10
        mock_award.name = 'Booker Prize'
        mock_book.award = mock_award
        result = service._format_book(mock_book)
        assert result['id'] == 1
        assert result['title'] == 'Test Title'
        assert result['title_zh'] == '测试标题'
        assert result['source'] == 'award'
        assert result['award'] == {'id': 10, 'name': 'Booker Prize'}

    def test_formats_book_without_award(self, service):
        mock_book = Mock()
        mock_book.id = 2
        mock_book.title = 'No Award Book'
        mock_book.title_zh = None
        mock_book.author = 'Author'
        mock_book.publisher = 'Publisher'
        mock_book.year = 2023
        mock_book.category = 'Nonfiction'
        mock_book.rank = 5
        mock_book.cover_original_url = None
        mock_book.isbn13 = '9780000000000'
        mock_book.award = None
        result = service._format_book(mock_book)
        assert result['source'] == 'award'
        assert result['award'] is None
        assert result['cover_url'] is None


class TestFormatNewBook:
    def test_formats_new_book_with_publisher(self, service):
        mock_book = Mock()
        mock_book.id = 1
        mock_book.title = 'New Book'
        mock_book.author = 'Author'
        mock_book.category = 'Fiction'
        mock_book.cover_url = 'http://example.com/cover.jpg'
        mock_book.isbn13 = '9781234567890'
        mock_book.title_zh = '新书标题'
        mock_book.publication_date = datetime(2024, 6, 15, tzinfo=UTC).date()
        mock_publisher = Mock()
        mock_publisher.name = 'Penguin Books'
        mock_book.publisher = mock_publisher
        result = service._format_new_book(mock_book)
        assert result['id'] == 1
        assert result['title'] == 'New Book'
        assert result['title_zh'] == '新书标题'
        assert result['publisher'] == 'Penguin Books'
        assert result['year'] == 2024
        assert result['source'] == 'new_book'
        assert result['rank'] is None
        assert result['award'] is None

    def test_formats_new_book_without_publisher(self, service):
        mock_book = Mock()
        mock_book.id = 2
        mock_book.title = 'No Publisher Book'
        mock_book.author = 'Author'
        mock_book.category = None
        mock_book.cover_url = None
        mock_book.isbn13 = None
        mock_book.title_zh = None
        mock_book.publication_date = None
        mock_book.publisher = None
        result = service._format_new_book(mock_book)
        assert result['publisher'] is None
        assert result['year'] is None
        assert result['title_zh'] is None


class TestSearch:
    def test_empty_keyword_returns_empty(self, service):
        result = service.search('')
        assert result['results'] == []
        assert result['total'] == 0
        assert result['keyword'] == ''

    def test_sanitize_keyword(self, service, app):
        with app.app_context():
            award_q = _make_flask_query([], count_val=0)
            new_q = _make_flask_query([], count_val=0)
            with (
                patch.object(service, '_apply_award_search_conditions', return_value=award_q),
                patch.object(service, '_apply_new_book_search_conditions', return_value=new_q),
            ):
                result = service.search('  hello  ')
                assert result['keyword'] == 'hello'

    def test_limit_clamped_to_100(self, service, app):
        with app.app_context():
            award_q = _make_flask_query([], count_val=0)
            new_q = _make_flask_query([], count_val=0)
            with (
                patch.object(service, '_apply_award_search_conditions', return_value=award_q),
                patch.object(service, '_apply_new_book_search_conditions', return_value=new_q),
            ):
                result = service.search('test', limit=200)
                assert result['pagination']['limit'] == 100

    def test_offset_clamped_to_positive(self, service, app):
        with (
            app.app_context(),
            patch.object(
                service,
                '_apply_award_search_conditions',
                return_value=Mock(filter=Mock(return_value=Mock(count=Mock(return_value=0)))),
            ),
            patch.object(
                service,
                '_apply_new_book_search_conditions',
                return_value=Mock(filter=Mock(return_value=Mock(count=Mock(return_value=0)))),
            ),
        ):
            result = service.search('test', offset=-5)
            assert result['pagination']['offset'] == 0

    def test_search_exception_returns_empty(self, service):
        with patch.object(service, '_sanitize_keyword', side_effect=Exception('Unexpected')):
            result = service.search('test')
            assert result['results'] == []
            assert result['total'] == 0

    def test_search_has_more_pagination(self, service, app):
        with app.app_context():
            award_q = Mock()
            award_q.filter.return_value = award_q
            award_q.count.return_value = 50
            award_q.order_by.return_value = award_q
            award_q.offset.return_value = award_q
            award_q.limit.return_value = award_q
            award_q.all.return_value = []

            new_q = Mock()
            new_q.filter.return_value = new_q
            new_q.count.return_value = 0
            new_q.order_by.return_value = new_q
            new_q.offset.return_value = new_q
            new_q.limit.return_value = new_q
            new_q.all.return_value = []

            with (
                patch.object(service, '_apply_award_search_conditions', return_value=award_q),
                patch.object(service, '_apply_new_book_search_conditions', return_value=new_q),
            ):
                result = service.search('test', limit=10, offset=0)
                assert result['pagination']['has_more'] is True

    def test_search_returns_formatted_results(self, service, app):
        with app.app_context():
            mock_book = Mock()
            mock_book.id = 1
            mock_book.title = 'Found Book'
            mock_book.title_zh = None
            mock_book.author = 'Author'
            mock_book.publisher = 'Publisher'
            mock_book.year = 2024
            mock_book.category = 'Fiction'
            mock_book.rank = 1
            mock_book.cover_original_url = None
            mock_book.isbn13 = '123'
            mock_book.award_id = 1
            mock_book.award = Mock(name='Test Award')

            award_q = Mock()
            award_q.filter.return_value = award_q
            award_q.count.return_value = 1
            award_q.order_by.return_value = award_q
            award_q.offset.return_value = award_q
            award_q.limit.return_value = award_q
            award_q.all.return_value = [mock_book]

            new_q = Mock()
            new_q.filter.return_value = new_q
            new_q.count.return_value = 0
            new_q.order_by.return_value = new_q
            new_q.offset.return_value = new_q
            new_q.limit.return_value = new_q
            new_q.all.return_value = []

            with (
                patch.object(service, '_apply_award_search_conditions', return_value=award_q),
                patch.object(service, '_apply_new_book_search_conditions', return_value=new_q),
            ):
                result = service.search('test')
                assert result['total'] == 1
                assert len(result['results']) == 1
                assert result['results'][0]['title'] == 'Found Book'


class TestApplyAwardSearchConditions:
    def test_search_type_all(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.schemas import AwardBook

        with (
            patch.object(AwardBook, 'title') as mock_title,
            patch.object(AwardBook, 'title_zh') as mock_title_zh,
            patch.object(AwardBook, 'author') as mock_author,
            patch.object(AwardBook, 'publisher') as mock_publisher,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_title.ilike.return_value = dummy_cond
            mock_title_zh.ilike.return_value = dummy_cond
            mock_author.ilike.return_value = dummy_cond
            mock_publisher.ilike.return_value = dummy_cond
            service._apply_award_search_conditions(mock_query, 'test', 'all')
            mock_query.filter.assert_called_once()

    def test_search_type_title_only(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.schemas import AwardBook

        with (
            patch.object(AwardBook, 'title') as mock_title,
            patch.object(AwardBook, 'title_zh') as mock_title_zh,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_title.ilike.return_value = dummy_cond
            mock_title_zh.ilike.return_value = dummy_cond
            service._apply_award_search_conditions(mock_query, 'test', 'title')
            mock_query.filter.assert_called_once()

    def test_search_type_author_only(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.schemas import AwardBook

        with (
            patch.object(AwardBook, 'author') as mock_author,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_author.ilike.return_value = dummy_cond
            service._apply_award_search_conditions(mock_query, 'test', 'author')
            mock_query.filter.assert_called_once()

    def test_search_type_publisher_only(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.schemas import AwardBook

        with (
            patch.object(AwardBook, 'publisher') as mock_publisher,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_publisher.ilike.return_value = dummy_cond
            service._apply_award_search_conditions(mock_query, 'test', 'publisher')
            mock_query.filter.assert_called_once()

    def test_escapes_special_characters(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.schemas import AwardBook

        with (
            patch.object(AwardBook, 'title') as mock_title,
            patch.object(AwardBook, 'title_zh') as mock_title_zh,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_title.ilike.return_value = dummy_cond
            mock_title_zh.ilike.return_value = dummy_cond
            service._apply_award_search_conditions(mock_query, '100%_test', 'title')
            mock_title.ilike.assert_called_with('%100\\%\\_test%')


class TestApplyNewBookSearchConditions:
    def test_search_type_all(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.new_book import NewBook

        with (
            patch.object(NewBook, 'title') as mock_title,
            patch.object(NewBook, 'title_zh') as mock_title_zh,
            patch.object(NewBook, 'author') as mock_author,
            patch.object(NewBook, 'isbn13') as mock_isbn,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_title.ilike.return_value = dummy_cond
            mock_title_zh.ilike.return_value = dummy_cond
            mock_author.ilike.return_value = dummy_cond
            mock_isbn.ilike.return_value = dummy_cond
            service._apply_new_book_search_conditions(mock_query, 'test', 'all')
            mock_query.filter.assert_called_once()

    def test_search_type_title_only(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.new_book import NewBook

        with (
            patch.object(NewBook, 'title') as mock_title,
            patch.object(NewBook, 'title_zh') as mock_title_zh,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_title.ilike.return_value = dummy_cond
            mock_title_zh.ilike.return_value = dummy_cond
            service._apply_new_book_search_conditions(mock_query, 'test', 'title')
            mock_query.filter.assert_called_once()

    def test_search_type_author_only(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.new_book import NewBook

        with (
            patch.object(NewBook, 'author') as mock_author,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_author.ilike.return_value = dummy_cond
            service._apply_new_book_search_conditions(mock_query, 'test', 'author')
            mock_query.filter.assert_called_once()

    def test_search_type_publisher_uses_isbn(self, service):
        mock_query = Mock()
        mock_query.filter.return_value = mock_query
        dummy_cond = text('1=1')
        from app.models.new_book import NewBook

        with (
            patch.object(NewBook, 'isbn13') as mock_isbn,
            patch('app.services.smart_search_service.or_', return_value=dummy_cond),
        ):
            mock_isbn.ilike.return_value = dummy_cond
            service._apply_new_book_search_conditions(mock_query, 'test', 'publisher')
            mock_query.filter.assert_called_once()


class TestGenerateSuggestions:
    def test_returns_suggestions_from_history(self, service):
        mock_search1 = Mock()
        mock_search1.keyword = 'hello world'
        mock_search2 = Mock()
        mock_search2.keyword = 'hello there'
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = [mock_search1, mock_search2]
            MockSH.query = mock_q
            MockSH.keyword = Mock()
            MockSH.created_at = Mock()
            MockSH.id = Mock()
            result = service._generate_suggestions('hello', 'all')
            assert 'hello world' in result
            assert 'hello there' in result

    def test_deduplicates_suggestions(self, service):
        mock_search1 = Mock()
        mock_search1.keyword = 'hello'
        mock_search2 = Mock()
        mock_search2.keyword = 'Hello'
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.filter.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = [mock_search1, mock_search2]
            MockSH.query = mock_q
            MockSH.keyword = Mock()
            MockSH.created_at = Mock()
            MockSH.id = Mock()
            result = service._generate_suggestions('hel', 'all')
            assert len(result) <= 2

    def test_exception_returns_empty(self, service):
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            MockSH.query = Mock(side_effect=Exception('DB error'))
            result = service._generate_suggestions('hello', 'all')
            assert result == []


class TestGetSuggestions:
    def test_empty_prefix_returns_empty(self, service):
        result = service.get_suggestions('')
        assert result['suggestions'] == []
        assert result['prefix'] == ''

    def test_limit_clamped(self, service):
        dummy_cond = text('1=1')
        with patch('app.services.smart_search_service.AwardBook') as MockAward:
            mock_q = _make_flask_query([])
            MockAward.query = mock_q
            MockAward.is_displayable = dummy_cond
            MockAward.title = Mock()
            MockAward.title.ilike.return_value = dummy_cond
            MockAward.title_zh = Mock()
            MockAward.title_zh.ilike.return_value = dummy_cond
            MockAward.author = Mock()
            MockAward.author.ilike.return_value = dummy_cond
            MockAward.publisher = Mock()
            MockAward.publisher.ilike.return_value = dummy_cond
            result = service.get_suggestions('test', limit=100)
            assert len(result['suggestions']) <= 20

    def test_suggestions_from_titles(self, service):
        dummy_cond = text('1=1')
        with patch('app.services.smart_search_service.AwardBook') as MockAward:
            mock_q = _make_flask_query([('Test Book Title',)])
            MockAward.query = mock_q
            MockAward.is_displayable = dummy_cond
            MockAward.title = Mock()
            MockAward.title.ilike.return_value = dummy_cond
            MockAward.title_zh = Mock()
            MockAward.title_zh.ilike.return_value = dummy_cond
            MockAward.author = Mock()
            MockAward.author.ilike.return_value = dummy_cond
            MockAward.publisher = Mock()
            MockAward.publisher.ilike.return_value = dummy_cond
            result = service.get_suggestions('test')
            assert len(result['suggestions']) > 0
            assert result['suggestions'][0]['type'] == 'title'

    def test_suggestions_from_authors(self, service):
        dummy_cond = text('1=1')
        with patch('app.services.smart_search_service.AwardBook') as MockAward:
            empty_q = _make_flask_query([])
            author_q = _make_flask_query([('Test Author',)])
            MockAward.query = Mock()
            MockAward.query.filter.side_effect = [empty_q, author_q]
            MockAward.query.filter.return_value = empty_q
            MockAward.is_displayable = dummy_cond
            MockAward.title = Mock()
            MockAward.title.ilike.return_value = dummy_cond
            MockAward.title_zh = Mock()
            MockAward.title_zh.ilike.return_value = dummy_cond
            MockAward.author = Mock()
            MockAward.author.ilike.return_value = dummy_cond
            MockAward.publisher = Mock()
            MockAward.publisher.ilike.return_value = dummy_cond
            result = service.get_suggestions('test')
            assert isinstance(result['suggestions'], list)

    def test_suggestions_from_publishers(self, service):
        dummy_cond = text('1=1')
        with patch('app.services.smart_search_service.AwardBook') as MockAward:
            empty_q = _make_flask_query([])
            pub_q = _make_flask_query([('Penguin Books',)])
            MockAward.query = Mock()
            MockAward.query.filter.side_effect = [empty_q, empty_q, pub_q]
            MockAward.query.filter.return_value = empty_q
            MockAward.is_displayable = dummy_cond
            MockAward.title = Mock()
            MockAward.title.ilike.return_value = dummy_cond
            MockAward.title_zh = Mock()
            MockAward.title_zh.ilike.return_value = dummy_cond
            MockAward.author = Mock()
            MockAward.author.ilike.return_value = dummy_cond
            MockAward.publisher = Mock()
            MockAward.publisher.ilike.return_value = dummy_cond
            result = service.get_suggestions('pen')
            pub_suggestions = [s for s in result['suggestions'] if s['type'] == 'publisher']
            assert len(pub_suggestions) > 0

    def test_deduplication(self, service):
        dummy_cond = text('1=1')
        with patch('app.services.smart_search_service.AwardBook') as MockAward:
            mock_q = _make_flask_query([('Same Title',), ('same title',)])
            MockAward.query = mock_q
            MockAward.is_displayable = dummy_cond
            MockAward.title = Mock()
            MockAward.title.ilike.return_value = dummy_cond
            MockAward.title_zh = Mock()
            MockAward.title_zh.ilike.return_value = dummy_cond
            MockAward.author = Mock()
            MockAward.author.ilike.return_value = dummy_cond
            MockAward.publisher = Mock()
            MockAward.publisher.ilike.return_value = dummy_cond
            result = service.get_suggestions('same')
            texts = [s['text'] for s in result['suggestions']]
            assert len(texts) == len(set(t.lower() for t in texts))

    def test_exception_returns_error(self, service):
        dummy_cond = text('1=1')
        with patch('app.services.smart_search_service.AwardBook') as MockAward:
            MockAward.query = Mock(side_effect=Exception('DB error'))
            MockAward.is_displayable = dummy_cond
            MockAward.title = Mock()
            MockAward.title.ilike.return_value = dummy_cond
            result = service.get_suggestions('test')
            assert result['suggestions'] == []
            assert 'error' in result


class TestGetPopularSearches:
    def test_returns_popular_searches(self, service):
        mock_item1 = ('python', 10, datetime(2024, 1, 1, tzinfo=UTC))
        mock_item2 = ('javascript', 5, datetime(2024, 1, 2, tzinfo=UTC))
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.with_entities.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = [mock_item1, mock_item2]
            MockSH.query = mock_q
            MockSH.keyword = Mock()
            MockSH.id = Mock()
            MockSH.created_at = Mock()
            result = service.get_popular_searches()
            assert result['total'] == 2
            assert result['popular_searches'][0]['keyword'] == 'python'
            assert result['popular_searches'][0]['count'] == 10

    def test_limit_clamped(self, service):
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.with_entities.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []
            MockSH.query = mock_q
            MockSH.keyword = Mock()
            MockSH.id = Mock()
            MockSH.created_at = Mock()
            result = service.get_popular_searches(limit=200)
            mock_q.limit.assert_called_with(50)

    def test_exception_returns_empty(self, service):
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            MockSH.query = Mock(side_effect=Exception('DB error'))
            result = service.get_popular_searches()
            assert result['popular_searches'] == []
            assert result['total'] == 0
            assert 'error' in result

    def test_handles_none_last_search(self, service):
        mock_item = ('python', 10, None)
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.with_entities.return_value = mock_q
            mock_q.group_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = [mock_item]
            MockSH.query = mock_q
            MockSH.keyword = Mock()
            MockSH.id = Mock()
            MockSH.created_at = Mock()
            result = service.get_popular_searches()
            assert result['popular_searches'][0]['last_searched'] is None


class TestSaveSearchHistory:
    def test_saves_history(self, service):
        with (
            patch('app.services.smart_search_service.db') as mock_db,
            patch('app.services.smart_search_service.SearchHistory') as MockSH,
        ):
            result = service.save_search_history('session1', 'python books', 5)
            assert result is True
            mock_db.session.merge.assert_called_once()
            mock_db.session.commit.assert_called_once()

    def test_empty_keyword_returns_false(self, service):
        result = service.save_search_history('session1', '', 0)
        assert result is False

    def test_exception_returns_false(self, service):
        with (
            patch('app.services.smart_search_service.db') as mock_db,
            patch('app.services.smart_search_service.SearchHistory') as MockSH,
        ):
            mock_db.session.merge.side_effect = Exception('DB error')
            result = service.save_search_history('session1', 'python', 5)
            assert result is False
            mock_db.session.rollback.assert_called_once()


class TestGetSearchHistory:
    def test_returns_keywords(self, service):
        mock_h1 = Mock()
        mock_h1.keyword = 'python'
        mock_h2 = Mock()
        mock_h2.keyword = 'javascript'
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.filter_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = [mock_h1, mock_h2]
            MockSH.query = mock_q
            MockSH.created_at = Mock()
            result = service.get_search_history('session1')
            assert result == ['python', 'javascript']

    def test_deduplicates_keywords(self, service):
        mock_h1 = Mock()
        mock_h1.keyword = 'python'
        mock_h2 = Mock()
        mock_h2.keyword = 'Python'
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.filter_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = [mock_h1, mock_h2]
            MockSH.query = mock_q
            MockSH.created_at = Mock()
            result = service.get_search_history('session1')
            assert len(result) == 1

    def test_limit_clamped(self, service):
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            mock_q = Mock()
            mock_q.filter_by.return_value = mock_q
            mock_q.order_by.return_value = mock_q
            mock_q.limit.return_value = mock_q
            mock_q.all.return_value = []
            MockSH.query = mock_q
            MockSH.created_at = Mock()
            service.get_search_history('session1', limit=200)
            mock_q.limit.assert_called_with(50)

    def test_exception_returns_empty(self, service):
        with patch('app.services.smart_search_service.SearchHistory') as MockSH:
            MockSH.query = Mock(side_effect=Exception('DB error'))
            result = service.get_search_history('session1')
            assert result == []


class TestClearSearchHistory:
    def test_clears_history(self, service):
        with (
            patch('app.services.smart_search_service.db') as mock_db,
            patch('app.services.smart_search_service.SearchHistory') as MockSH,
        ):
            mock_q = Mock()
            mock_q.delete.return_value = 5
            MockSH.query.filter_by.return_value = mock_q
            result = service.clear_search_history('session1')
            assert result is True
            mock_db.session.commit.assert_called_once()

    def test_exception_returns_false(self, service):
        with (
            patch('app.services.smart_search_service.db') as mock_db,
            patch('app.services.smart_search_service.SearchHistory') as MockSH,
        ):
            mock_q = Mock()
            mock_q.delete.side_effect = Exception('DB error')
            MockSH.query.filter_by.return_value = mock_q
            result = service.clear_search_history('session1')
            assert result is False
            mock_db.session.rollback.assert_called_once()
