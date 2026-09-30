import pytest
from pydantic import ValidationError
from werkzeug.datastructures import MultiDict

from app.schemas.validators import (
    NewBookExportQuery,
    NewBookListQuery,
    NewBookSearchQuery,
    NewBookSyncQuery,
    parse_query_args,
)


class TestNewBookListQuery:
    def test_defaults(self):
        req = NewBookListQuery()
        assert req.publisher_id is None
        assert req.category is None
        # 维护者决议（2026-08-07）：出版 30 天内才算"新书"
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


@pytest.mark.parametrize(
    ('model_cls', 'kwargs', 'expected_days'),
    [
        (NewBookListQuery, {}, 30),
        (NewBookSearchQuery, {'keyword': 'python'}, None),
        (NewBookExportQuery, {}, 30),
    ],
)
def test_publication_status_defaults_keep_original_days(model_cls, kwargs, expected_days):
    req = model_cls(**kwargs)
    assert req.publication_status == 'all'
    assert req.days == expected_days
    if model_cls is NewBookExportQuery:
        assert req.search == ''


@pytest.mark.parametrize('model_cls', [NewBookListQuery, NewBookSearchQuery, NewBookExportQuery])
@pytest.mark.parametrize('status', ['all', 'published', 'upcoming', 'pending'])
def test_allowed_publication_statuses(model_cls, status):
    kwargs = {'publication_status': status}
    if model_cls is NewBookSearchQuery:
        kwargs['keyword'] = 'python'
    assert model_cls(**kwargs).publication_status == status


@pytest.mark.parametrize('model_cls', [NewBookListQuery, NewBookSearchQuery, NewBookExportQuery])
@pytest.mark.parametrize('status', ['not-a-status', ''])
def test_illegal_publication_status_rejected(model_cls, status):
    kwargs = {'publication_status': status}
    if model_cls is NewBookSearchQuery:
        kwargs['keyword'] = 'python'
    with pytest.raises(ValidationError):
        model_cls(**kwargs)


@pytest.mark.parametrize(
    ('model_cls', 'raw_status', 'expected', 'extra'),
    [
        (NewBookListQuery, '  published  ', 'published', {}),
        (NewBookSearchQuery, ' upcoming ', 'upcoming', {'keyword': 'python'}),
        (NewBookExportQuery, ' pending ', 'pending', {'search': '  isle  '}),
    ],
)
def test_parse_strips_status_and_export_search(model_cls, raw_status, expected, extra):
    req = parse_query_args(model_cls, MultiDict({'publication_status': raw_status, **extra}))
    assert req.publication_status == expected
    if model_cls is NewBookExportQuery:
        assert req.search == 'isle'
        with pytest.raises(ValidationError):
            NewBookExportQuery(search='x' * 101)
