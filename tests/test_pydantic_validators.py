import pytest
from pydantic import ValidationError
from werkzeug.datastructures import MultiDict

from app.schemas.validators import (
    AwardBooksQuery,
    BookSearchRequest,
    CacheClearRequest,
    NewBookExportQuery,
    NewBookListQuery,
    NewBookSearchQuery,
    NewBookSyncQuery,
    PaginationParams,
    RecommendationQuery,
    SmartSearchQuery,
    TranslateBookFieldsRequest,
    TranslateRequest,
    UserPreferencesUpdate,
    parse_query_args,
)


class TestBookSearchRequest:
    def test_valid_keyword(self):
        req = BookSearchRequest(keyword='python')
        assert req.keyword == 'python'

    def test_keyword_too_short(self):
        with pytest.raises(ValidationError):
            BookSearchRequest(keyword='a')

    def test_keyword_too_long(self):
        with pytest.raises(ValidationError):
            BookSearchRequest(keyword='x' * 101)

    def test_keyword_chinese(self):
        req = BookSearchRequest(keyword='Python编程')
        assert req.keyword == 'Python编程'

    def test_keyword_invalid_chars(self):
        with pytest.raises(ValidationError):
            BookSearchRequest(keyword='<script>alert(1)</script>')


class TestTranslateRequest:
    def test_valid_request(self):
        req = TranslateRequest(text='Hello')
        assert req.text == 'Hello'
        assert req.source_lang == 'en'
        assert req.target_lang == 'zh'

    def test_empty_text(self):
        with pytest.raises(ValidationError):
            TranslateRequest(text='')

    def test_text_too_long(self):
        with pytest.raises(ValidationError):
            TranslateRequest(text='x' * 10001)

    def test_invalid_lang_code(self):
        with pytest.raises(ValidationError):
            TranslateRequest(text='Hello', source_lang='english')


class TestTranslateBookFieldsRequest:
    def test_has_any_field_true(self):
        req = TranslateBookFieldsRequest(title='Test')
        assert req.has_any_field() is True

    def test_has_any_field_false(self):
        req = TranslateBookFieldsRequest()
        assert req.has_any_field() is False

    def test_total_length(self):
        req = TranslateBookFieldsRequest(title='Hello', description='World')
        assert req.total_length == 10

    def test_strip_whitespace(self):
        req = TranslateBookFieldsRequest(title='  Test  ')
        assert req.title == 'Test'


class TestPaginationParams:
    def test_defaults(self):
        req = PaginationParams()
        assert req.page == 1
        assert req.limit == 20

    def test_page_zero(self):
        with pytest.raises(ValidationError):
            PaginationParams(page=0)

    def test_limit_too_large(self):
        with pytest.raises(ValidationError):
            PaginationParams(limit=51)


class TestAwardBooksQuery:
    def test_defaults(self):
        req = AwardBooksQuery()
        assert req.award_id is None
        assert req.year is None

    def test_year_out_of_range(self):
        with pytest.raises(ValidationError):
            AwardBooksQuery(year=1800)
        with pytest.raises(ValidationError):
            AwardBooksQuery(year=2200)

    def test_valid_year(self):
        req = AwardBooksQuery(year=2024)
        assert req.year == 2024


class TestUserPreferencesUpdate:
    def test_valid_view_mode(self):
        req = UserPreferencesUpdate(view_mode='grid')
        assert req.view_mode == 'grid'

    def test_invalid_view_mode(self):
        with pytest.raises(ValidationError):
            UserPreferencesUpdate(view_mode='invalid')

    def test_none_view_mode(self):
        req = UserPreferencesUpdate(view_mode=None)
        assert req.view_mode is None


class TestRecommendationQuery:
    def test_defaults(self):
        req = RecommendationQuery()
        assert req.strategy == 'personalized'
        assert req.limit == 10

    def test_invalid_strategy_fallback(self):
        req = RecommendationQuery(strategy='invalid')
        assert req.strategy == 'personalized'

    def test_valid_strategies(self):
        for strategy in ('personalized', 'similarity', 'smart', 'popular'):
            req = RecommendationQuery(strategy=strategy)
            assert req.strategy == strategy


class TestSmartSearchQuery:
    def test_defaults(self):
        req = SmartSearchQuery()
        assert req.search_type == 'all'

    def test_invalid_search_type_fallback(self):
        req = SmartSearchQuery(search_type='invalid')
        assert req.search_type == 'all'

    def test_valid_search_types(self):
        for st in ('all', 'title', 'author', 'publisher'):
            req = SmartSearchQuery(search_type=st)
            assert req.search_type == st


class TestCacheClearRequest:
    def test_defaults(self):
        req = CacheClearRequest()
        assert req.older_than_days is None
        assert req.min_usage is None
        assert req.cache_id is None

    def test_negative_values(self):
        with pytest.raises(ValidationError):
            CacheClearRequest(older_than_days=0)
        with pytest.raises(ValidationError):
            CacheClearRequest(min_usage=-1)


# ============================================================
# v0.9.63 新增：新书模块 Pydantic 验证
# ============================================================


class TestNewBookListQuery:
    def test_defaults(self):
        req = NewBookListQuery()
        assert req.publisher_id is None
        assert req.category is None
        assert req.days == 30
        assert req.search == ''
        assert req.page == 1
        assert req.per_page == 20

    def test_days_too_large(self):
        with pytest.raises(ValidationError):
            NewBookListQuery(days=400)

    def test_days_too_small(self):
        with pytest.raises(ValidationError):
            NewBookListQuery(days=0)

    def test_per_page_too_large(self):
        with pytest.raises(ValidationError):
            NewBookListQuery(per_page=51)

    def test_search_too_long(self):
        with pytest.raises(ValidationError):
            NewBookListQuery(search='x' * 101)

    def test_valid_full(self):
        req = NewBookListQuery(publisher_id=2, category='Fiction', days=60, search='python', page=2, per_page=30)
        assert req.publisher_id == 2
        assert req.days == 60
        assert req.search == 'python'


class TestNewBookSearchQuery:
    def test_valid(self):
        req = NewBookSearchQuery(keyword='python')
        assert req.keyword == 'python'

    def test_keyword_too_short(self):
        with pytest.raises(ValidationError):
            NewBookSearchQuery(keyword='')

    def test_keyword_too_long(self):
        with pytest.raises(ValidationError):
            NewBookSearchQuery(keyword='x' * 101)

    def test_page_too_large(self):
        with pytest.raises(ValidationError):
            NewBookSearchQuery(keyword='python', page=10001)


class TestNewBookExportQuery:
    def test_defaults(self):
        req = NewBookExportQuery()
        assert req.publisher_id is None
        assert req.category is None
        assert req.days == 30

    def test_days_out_of_range(self):
        with pytest.raises(ValidationError):
            NewBookExportQuery(days=500)


class TestNewBookSyncQuery:
    def test_default(self):
        req = NewBookSyncQuery()
        assert req.max_books == 30

    def test_too_large(self):
        with pytest.raises(ValidationError):
            NewBookSyncQuery(max_books=101)


class TestParseQueryArgsHelper:
    """v0.9.63 新增：parse_query_args 工具函数。"""

    def test_strips_string_fields(self):
        args = MultiDict({'keyword': '  python  '})
        req = parse_query_args(NewBookSearchQuery, args)
        assert req.keyword == 'python'

    def test_handles_dict_fallback(self):
        """非 MultiDict 字典（mock 测试用）也能用。"""
        args = {'keyword': 'python'}
        req = parse_query_args(NewBookSearchQuery, args)
        assert req.keyword == 'python'

    def test_invalid_int_raises(self):
        args = MultiDict({'keyword': 'python', 'days': 'abc'})
        with pytest.raises(ValidationError):
            parse_query_args(NewBookListQuery, args)

    def test_days_defaults_when_missing(self):
        args = MultiDict({})
        req = parse_query_args(NewBookListQuery, args)
        assert req.days == 30
