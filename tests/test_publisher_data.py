"""publisher_data 模块单元测试"""

from datetime import date, datetime

from app.services.publisher_data import (
    CRAWLER_MIGRATION,
    DEFAULT_PUBLISHERS,
    GOOGLE_BOOKS_CRAWLERS,
    STATIC_DATA_FILES,
    VALID_CATEGORIES,
    coerce_publication_date,
    normalize_isbn,
    parse_int_safe,
    parse_static_date,
    sanitize_category,
)


class TestConstants:
    def test_default_publishers_has_seven_entries(self):
        assert len(DEFAULT_PUBLISHERS) == 7

    def test_static_data_files_match_publishers(self):
        """确保 STATIC_DATA_FILES 的 publisher name 在 DEFAULT_PUBLISHERS 中"""
        publisher_names = {p['name_en'] for p in DEFAULT_PUBLISHERS}
        for publisher_name in STATIC_DATA_FILES.values():
            assert publisher_name in publisher_names, f'{publisher_name} 不在 DEFAULT_PUBLISHERS 中'

    def test_valid_categories_is_set(self):
        assert isinstance(VALID_CATEGORIES, set)
        assert len(VALID_CATEGORIES) >= 20

    def test_crawler_migration_maps_to_known_crawlers(self):
        known = {p['crawler_class'] for p in DEFAULT_PUBLISHERS}
        for new_class in CRAWLER_MIGRATION.values():
            assert new_class in known, f'{new_class} 不在已知爬虫中'

    def test_google_books_crawlers_includes_penguin_random_house(self):
        assert 'PenguinRandomHouseCrawler' in GOOGLE_BOOKS_CRAWLERS


class TestSanitizeCategory:
    def test_returns_none_for_none(self):
        assert sanitize_category(None) is None

    def test_returns_none_for_empty(self):
        assert sanitize_category('') is None

    def test_returns_valid_category(self):
        assert sanitize_category('小说') == '小说'
        assert sanitize_category('Fiction') == 'Fiction'

    def test_rejects_marketing_keyword(self):
        assert sanitize_category('Learn more about books') is None
        assert sanitize_category('how to cook') is None
        assert sanitize_category('new releases today') is None
        assert sanitize_category('audiobook club') is None

    def test_rejects_too_long(self):
        assert sanitize_category('A' * 31) is None

    def test_rejects_url(self):
        assert sanitize_category('https://example.com') is None
        assert sanitize_category('click http://foo') is None

    def test_rejects_special_chars(self):
        assert sanitize_category('test>here') is None
        assert sanitize_category('test!here') is None

    def test_strips_whitespace(self):
        assert sanitize_category('  小说  ') == '小说'


class TestNormalizeIsbn:
    def test_returns_none_for_empty(self):
        assert normalize_isbn('', 13) is None
        assert normalize_isbn(None, 10) is None

    def test_valid_isbn13(self):
        assert normalize_isbn('9783161484100', 13) == '9783161484100'

    def test_valid_isbn10(self):
        assert normalize_isbn('0306406152', 10) == '0306406152'

    def test_isbn10_with_x(self):
        assert normalize_isbn('080442957X', 10) == '080442957X'
        assert normalize_isbn('080442957x', 10) == '080442957X'

    def test_strips_hyphens_and_spaces(self):
        assert normalize_isbn('978-3-16-148410-0', 13) == '9783161484100'
        assert normalize_isbn('0 306 40615 2', 10) == '0306406152'

    def test_returns_none_for_wrong_length(self):
        assert normalize_isbn('9783161484100', 10) is None
        assert normalize_isbn('0306406152', 13) is None

    def test_strips_non_isbn_chars(self):
        assert normalize_isbn('ISBN:9783161484100', 13) == '9783161484100'


class TestParseStaticDate:
    def test_returns_none_for_empty(self):
        assert parse_static_date(None) is None
        assert parse_static_date('') is None

    def test_iso_format(self):
        result = parse_static_date('2024-06-15')
        assert result == date(2024, 6, 15)

    def test_year_month_format(self):
        result = parse_static_date('2024-06')
        assert result == date(2024, 6, 1)

    def test_year_only_format(self):
        result = parse_static_date('2024')
        assert result == date(2024, 1, 1)

    def test_passes_through_date_object(self):
        d = date(2024, 6, 15)
        assert parse_static_date(d) == d

    def test_converts_datetime_to_date(self):
        dt = datetime(2024, 6, 15, 10, 30)
        result = parse_static_date(dt)
        assert result == date(2024, 6, 15)

    def test_invalid_format_returns_none(self):
        assert parse_static_date('not-a-date') is None
        assert parse_static_date('15/06/2024') is None


class TestCoercePublicationDate:
    def test_returns_none_for_empty(self):
        assert coerce_publication_date(None) is None

    def test_converts_datetime(self):
        dt = datetime(2024, 1, 15)
        assert coerce_publication_date(dt) == date(2024, 1, 15)

    def test_passes_through_date(self):
        d = date(2024, 1, 15)
        assert coerce_publication_date(d) == d

    def test_parses_string(self):
        assert coerce_publication_date('2024-03-20') == date(2024, 3, 20)


class TestParseIntSafe:
    def test_returns_none_for_none(self):
        assert parse_int_safe(None) is None

    def test_returns_none_for_empty_string(self):
        assert parse_int_safe('') is None

    def test_parses_valid_int(self):
        assert parse_int_safe('42') == 42
        assert parse_int_safe(42) == 42

    def test_returns_none_for_invalid(self):
        assert parse_int_safe('abc') is None
        assert parse_int_safe('12.5') is None
