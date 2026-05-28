"""
book_detail_service 模块测试

测试 ISBN 校验、Google Books 数据获取与更新、图书翻译合并等核心功能
"""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from app.services.book_detail_service import (
    fetch_google_books_details,
    is_valid_isbn,
    merge_or_translate_book,
    update_book_from_google_books,
)


class TestIsValidIsbn:
    """测试 is_valid_isbn ISBN 校验函数"""

    def test_valid_isbn13_978_prefix(self):
        """有效的 ISBN-13（978 开头）"""
        assert is_valid_isbn('9780143127550') is True

    def test_valid_isbn13_979_prefix(self):
        """有效的 ISBN-13（979 开头）"""
        assert is_valid_isbn('9791234567897') is True

    def test_valid_isbn10_digit_check(self):
        """有效的 ISBN-10（末位为数字）"""
        assert is_valid_isbn('0143127550') is True

    def test_valid_isbn10_x_check_digit(self):
        """有效的 ISBN-10（末位为 X）"""
        assert is_valid_isbn('014312755X') is True

    def test_valid_isbn10_lowercase_x(self):
        """有效的 ISBN-10（末位为小写 x，函数会 uppercase 比较）"""
        assert is_valid_isbn('014312755x') is True

    def test_valid_isbn13_with_hyphens(self):
        """带连字符的 ISBN-13"""
        assert is_valid_isbn('978-0-14-312755-0') is True

    def test_valid_isbn10_with_hyphens(self):
        """带连字符的 ISBN-10"""
        assert is_valid_isbn('0-14-312755-X') is True

    def test_valid_isbn13_with_spaces(self):
        """带空格的 ISBN-13"""
        assert is_valid_isbn('978 0143127550') is True

    def test_valid_isbn10_with_spaces(self):
        """带空格的 ISBN-10"""
        assert is_valid_isbn('014312755 X') is True

    def test_valid_isbn13_with_mixed_separators(self):
        """同时带连字符和空格的 ISBN-13"""
        assert is_valid_isbn('978-014 312755-0') is True

    def test_none_input(self):
        """None 输入"""
        assert is_valid_isbn(None) is False

    def test_empty_string(self):
        """空字符串"""
        assert is_valid_isbn('') is False

    def test_invalid_isbn13_wrong_prefix(self):
        """ISBN-13 前缀不是 978/979"""
        assert is_valid_isbn('1230143127550') is False

    def test_invalid_isbn13_too_short(self):
        """ISBN-13 过短"""
        assert is_valid_isbn('97801431275') is False

    def test_invalid_isbn13_too_long(self):
        """ISBN-13 过长"""
        assert is_valid_isbn('97801431275501') is False

    def test_invalid_isbn13_non_digit(self):
        """ISBN-13 包含非数字字符"""
        assert is_valid_isbn('978014312755A') is False

    def test_invalid_isbn10_too_short(self):
        """ISBN-10 过短"""
        assert is_valid_isbn('01431275') is False

    def test_invalid_isbn10_too_long(self):
        """ISBN-10 过长"""
        assert is_valid_isbn('01431275501') is False

    def test_invalid_isbn10_non_digit_non_x(self):
        """ISBN-10 包含除数字和 X 以外的字符"""
        assert is_valid_isbn('014312755Y') is False

    def test_invalid_isbn10_x_not_at_end(self):
        """ISBN-10 中 X 不在末位"""
        assert is_valid_isbn('01431X7550') is False

    def test_pure_letters(self):
        """纯字母字符串"""
        assert is_valid_isbn('abcdefghijkl') is False

    def test_isbn13_with_only_hyphens(self):
        """只有连字符"""
        assert is_valid_isbn('-------------') is False


@patch('app.services.book_detail_service.translate_field_async')
class TestUpdateBookFromGoogleBooks:
    """测试 update_book_from_google_books 数据更新函数"""

    def test_updates_details_and_triggers_translation(self, mock_translate):
        """更新 details 字段并触发翻译"""
        book = {}
        details = {'details': 'A detailed book description.'}

        update_book_from_google_books(book, details)

        assert book['details'] == 'A detailed book description.'
        mock_translate.assert_called_once_with(book, 'details', 'details_zh')

    def test_skips_unknown_details(self, mock_translate):
        """details 为 'No detailed description available.' 时跳过"""
        book = {}
        details = {'details': 'No detailed description available.'}

        update_book_from_google_books(book, details)

        assert 'details' not in book
        mock_translate.assert_not_called()

    def test_skips_empty_details(self, mock_translate):
        """details 为空时跳过"""
        book = {}
        details = {'details': ''}

        update_book_from_google_books(book, details)

        assert 'details' not in book
        mock_translate.assert_not_called()

    def test_updates_page_count(self, mock_translate):
        """更新 page_count"""
        book = {}
        details = {'page_count': 320}

        update_book_from_google_books(book, details)

        assert book['page_count'] == '320'

    def test_skips_unknown_page_count(self, mock_translate):
        """page_count 为 Unknown 时跳过"""
        book = {}
        details = {'page_count': 'Unknown'}

        update_book_from_google_books(book, details)

        assert 'page_count' not in book

    def test_updates_publication_dt(self, mock_translate):
        """更新 publication_dt"""
        book = {}
        details = {'publication_dt': '2023-10-01'}

        update_book_from_google_books(book, details)

        assert book['publication_dt'] == '2023-10-01'

    def test_skips_unknown_publication_dt(self, mock_translate):
        """publication_dt 为 Unknown 时跳过"""
        book = {}
        details = {'publication_dt': 'Unknown'}

        update_book_from_google_books(book, details)

        assert 'publication_dt' not in book

    def test_updates_language(self, mock_translate):
        """更新 language"""
        book = {}
        details = {'language': 'en'}

        update_book_from_google_books(book, details)

        assert book['language'] == 'en'

    def test_skips_unknown_language(self, mock_translate):
        """language 为 Unknown 时跳过"""
        book = {}
        details = {'language': 'Unknown'}

        update_book_from_google_books(book, details)

        assert 'language' not in book

    def test_updates_publisher_when_book_has_unknown(self, mock_translate):
        """book 的 publisher 为 Unknown 时，用 details 的值覆盖"""
        book = {'publisher': 'Unknown'}
        details = {'publisher': 'Penguin'}

        update_book_from_google_books(book, details)

        assert book['publisher'] == 'Penguin'

    def test_updates_publisher_when_book_has_unknown_publisher(self, mock_translate):
        """book 的 publisher 为 'Unknown Publisher' 时覆盖"""
        book = {'publisher': 'Unknown Publisher'}
        details = {'publisher': 'HarperCollins'}

        update_book_from_google_books(book, details)

        assert book['publisher'] == 'HarperCollins'

    def test_preserves_existing_publisher(self, mock_translate):
        """book 已有有效 publisher 时不覆盖"""
        book = {'publisher': 'Existing Publisher'}
        details = {'publisher': 'New Publisher'}

        update_book_from_google_books(book, details)

        assert book['publisher'] == 'Existing Publisher'

    def test_preserves_existing_publisher_when_book_empty(self, mock_translate):
        """book 没有 publisher 字段时用 details 的值"""
        book = {}
        details = {'publisher': 'Penguin'}

        update_book_from_google_books(book, details)

        assert book['publisher'] == 'Penguin'

    def test_skips_unknown_publisher_from_details(self, mock_translate):
        """details 的 publisher 为 Unknown 时跳过"""
        book = {}
        details = {'publisher': 'Unknown'}

        update_book_from_google_books(book, details)

        assert 'publisher' not in book

    def test_skips_unknown_publisher_value(self, mock_translate):
        """details 的 publisher 为 'Unknown Publisher' 时跳过"""
        book = {}
        details = {'publisher': 'Unknown Publisher'}

        update_book_from_google_books(book, details)

        assert 'publisher' not in book

    def test_updates_cover_when_empty(self, mock_translate):
        """book 没有 cover 时，用 cover_url 填充"""
        book = {}
        details = {'cover_url': 'https://example.com/cover.jpg'}

        update_book_from_google_books(book, details)

        assert book['cover'] == 'https://example.com/cover.jpg'

    def test_preserves_existing_cover(self, mock_translate):
        """book 已有 cover 时不覆盖"""
        book = {'cover': 'https://existing.com/cover.jpg'}
        details = {'cover_url': 'https://new.com/cover.jpg'}

        update_book_from_google_books(book, details)

        assert book['cover'] == 'https://existing.com/cover.jpg'

    def test_updates_isbn13_when_empty(self, mock_translate):
        """book 没有 isbn13 时，用 details 的值填充"""
        book = {}
        details = {'isbn_13': '9780143127550'}

        update_book_from_google_books(book, details)

        assert book['isbn13'] == '9780143127550'

    def test_preserves_existing_isbn13(self, mock_translate):
        """book 已有 isbn13 时不覆盖"""
        book = {'isbn13': '9780062796200'}
        details = {'isbn_13': '9780143127550'}

        update_book_from_google_books(book, details)

        assert book['isbn13'] == '9780062796200'

    def test_skips_invalid_isbn13(self, mock_translate):
        """details 的 isbn_13 格式无效时跳过"""
        book = {}
        details = {'isbn_13': '12345'}

        update_book_from_google_books(book, details)

        assert 'isbn13' not in book

    def test_updates_isbn10_when_empty(self, mock_translate):
        """book 没有 isbn10 时，用 details 的值填充"""
        book = {}
        details = {'isbn_10': '014312755X'}

        update_book_from_google_books(book, details)

        assert book['isbn10'] == '014312755X'

    def test_preserves_existing_isbn10(self, mock_translate):
        """book 已有 isbn10 时不覆盖"""
        book = {'isbn10': '0062796208'}
        details = {'isbn_10': '014312755X'}

        update_book_from_google_books(book, details)

        assert book['isbn10'] == '0062796208'

    def test_skips_invalid_isbn10(self, mock_translate):
        """details 的 isbn_10 格式无效时跳过"""
        book = {}
        details = {'isbn_10': 'abc'}

        update_book_from_google_books(book, details)

        assert 'isbn10' not in book

    def test_triggers_description_translation(self, mock_translate):
        """book 有 description 但无 description_zh 时触发翻译"""
        book = {'description': 'A great book.'}
        details = {}

        update_book_from_google_books(book, details)

        mock_translate.assert_called_once_with(book, 'description', 'description_zh')

    def test_no_description_translation_when_zh_exists(self, mock_translate):
        """book 已有 description_zh 时不触发翻译"""
        book = {'description': 'A great book.', 'description_zh': '一本好书'}
        details = {}

        update_book_from_google_books(book, details)

        mock_translate.assert_not_called()

    def test_no_description_translation_when_no_description(self, mock_translate):
        """book 没有 description 时不触发翻译"""
        book = {}
        details = {}

        update_book_from_google_books(book, details)

        mock_translate.assert_not_called()

    def test_all_fields_update(self, mock_translate):
        """同时更新所有字段的完整场景"""
        book = {}
        details = {
            'details': 'Full details here.',
            'page_count': 400,
            'publication_dt': '2024-01-15',
            'language': 'en',
            'publisher': 'Simon & Schuster',
            'cover_url': 'https://example.com/cover.jpg',
            'isbn_13': '9780143127550',
            'isbn_10': '014312755X',
        }

        update_book_from_google_books(book, details)

        assert book['details'] == 'Full details here.'
        assert book['page_count'] == '400'
        assert book['publication_dt'] == '2024-01-15'
        assert book['language'] == 'en'
        assert book['publisher'] == 'Simon & Schuster'
        assert book['cover'] == 'https://example.com/cover.jpg'
        assert book['isbn13'] == '9780143127550'
        assert book['isbn10'] == '014312755X'

    def test_empty_details_no_fields_updated(self, mock_translate):
        """空 details 字典不更新任何字段"""
        book = {}
        details = {}

        update_book_from_google_books(book, details)

        assert book == {}


class TestFetchGoogleBooksDetails:
    """测试 fetch_google_books_details 获取与缓存"""

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_cache_hit(self, mock_get_bs, mock_get_gc, mock_update):
        """缓存命中时直接使用缓存数据"""
        cached_data = {'details': 'Cached description.'}
        mock_cache = MagicMock()
        mock_cache.get.return_value = cached_data
        mock_bs = MagicMock()
        mock_bs.cache = mock_cache
        mock_get_bs.return_value = mock_bs

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_cache.get.assert_called_once_with('google_books_detail:9780143127550')
        mock_update.assert_called_once_with(book, cached_data)
        mock_get_gc.assert_not_called()

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_cache_miss_api_success(self, mock_get_bs, mock_get_gc, mock_update):
        """缓存未命中，API 返回成功"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_bs = MagicMock()
        mock_bs.cache = mock_cache
        mock_get_bs.return_value = mock_bs

        api_data = {'details': 'API fetched description.'}
        mock_client = MagicMock()
        mock_client.fetch_book_details.return_value = api_data
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_client.fetch_book_details.assert_called_once_with('9780143127550')
        mock_update.assert_called_once_with(book, api_data)
        mock_cache.set.assert_called_once_with('google_books_detail:9780143127550', api_data, ttl=604800)

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_cache_miss_api_returns_none(self, mock_get_bs, mock_get_gc, mock_update):
        """缓存未命中，API 返回 None"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_bs = MagicMock()
        mock_bs.cache = mock_cache
        mock_get_bs.return_value = mock_bs

        mock_client = MagicMock()
        mock_client.fetch_book_details.return_value = None
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_update.assert_not_called()
        mock_cache.set.assert_not_called()

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_cache_miss_api_exception(self, mock_get_bs, mock_get_gc, mock_update):
        """缓存未命中，API 抛出异常"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_bs = MagicMock()
        mock_bs.cache = mock_cache
        mock_get_bs.return_value = mock_bs

        mock_client = MagicMock()
        mock_client.fetch_book_details.side_effect = RuntimeError('API error')
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_update.assert_not_called()

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_no_google_client(self, mock_get_bs, mock_get_gc, mock_update):
        """没有 Google Books 客户端时直接返回"""
        mock_get_bs.return_value = None
        mock_get_gc.return_value = None

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_update.assert_not_called()

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_no_book_service_no_cache(self, mock_get_bs, mock_get_gc, mock_update):
        """book_service 不存在时跳过缓存，直接调 API"""
        mock_get_bs.return_value = None

        api_data = {'details': 'From API.'}
        mock_client = MagicMock()
        mock_client.fetch_book_details.return_value = api_data
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_client.fetch_book_details.assert_called_once_with('9780143127550')
        mock_update.assert_called_once_with(book, api_data)

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_cache_read_exception_falls_through(self, mock_get_bs, mock_get_gc, mock_update):
        """缓存读取异常时降级到 API 调用"""
        mock_cache = MagicMock()
        mock_cache.get.side_effect = RuntimeError('cache read error')
        mock_bs = MagicMock()
        mock_bs.cache = mock_cache
        mock_get_bs.return_value = mock_bs

        api_data = {'details': 'From API after cache error.'}
        mock_client = MagicMock()
        mock_client.fetch_book_details.return_value = api_data
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_client.fetch_book_details.assert_called_once()
        mock_update.assert_called_once_with(book, api_data)

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_cache_write_exception_does_not_propagate(self, mock_get_bs, mock_get_gc, mock_update):
        """缓存写入异常不影响主流程"""
        mock_cache = MagicMock()
        mock_cache.get.return_value = None
        mock_cache.set.side_effect = RuntimeError('cache write error')
        mock_bs = MagicMock()
        mock_bs.cache = mock_cache
        mock_get_bs.return_value = mock_bs

        api_data = {'details': 'From API.'}
        mock_client = MagicMock()
        mock_client.fetch_book_details.return_value = api_data
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_update.assert_called_once_with(book, api_data)

    @patch('app.services.book_detail_service.update_book_from_google_books')
    @patch('app.services.book_detail_service.get_google_books_client')
    @patch('app.services.book_detail_service.get_book_service')
    def test_book_service_cache_get_exception(self, mock_get_bs, mock_get_gc, mock_update):
        """获取 book_service 时异常降级到 API"""
        mock_get_bs.side_effect = RuntimeError('service init error')

        api_data = {'details': 'From API.'}
        mock_client = MagicMock()
        mock_client.fetch_book_details.return_value = api_data
        mock_get_gc.return_value = mock_client

        book = {}
        fetch_google_books_details(book, '9780143127550')

        mock_update.assert_called_once_with(book, api_data)


class TestMergeOrTranslateBook:
    """测试 merge_or_translate_book 翻译合并"""

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_meta_found_all_translations_present(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts):
        """数据库中有完整的翻译元数据时直接使用"""
        mock_meta = SimpleNamespace(
            title_zh='已翻译书名',
            description_zh='已翻译简介',
            details_zh='已翻译详情',
        )
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = mock_meta
        mock_us_cls.return_value = mock_us

        mock_clean.side_effect = lambda text, _: text

        book = {'title': 'Test', 'description': 'Desc', 'details': 'Details'}
        merge_or_translate_book(book, '9780143127550')

        assert book['title_zh'] == '已翻译书名'
        assert book['description_zh'] == '已翻译简介'
        assert book['details_zh'] == '已翻译详情'
        mock_submit.assert_not_called()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_meta_found_partial_translations(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """数据库中有部分翻译时，补充缺失字段后触发异步翻译"""
        mock_meta = SimpleNamespace(
            title_zh='已翻译书名',
            description_zh=None,
            details_zh=None,
        )
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = mock_meta
        mock_us_cls.return_value = mock_us

        mock_clean.side_effect = lambda text, _: text

        with app.app_context():
            book = {'title': 'Test', 'description': 'Desc', 'details': 'Details'}
            merge_or_translate_book(book, '9780143127550')

            assert book['title_zh'] == '已翻译书名'
            assert 'description_zh' not in book
            assert 'details_zh' not in book
            mock_submit.assert_called_once()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_meta_not_found_needs_translation(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """数据库中无元数据时，判断是否需要翻译并提交异步任务"""
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = None
        mock_us_cls.return_value = mock_us

        mock_translation_service = MagicMock()
        mock_get_ts.return_value = mock_translation_service

        with app.app_context():
            book = {'title': 'Test', 'description': 'Desc', 'details': 'Details'}
            merge_or_translate_book(book, '9780143127550')

            mock_submit.assert_called_once()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_no_translation_service_available(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """翻译服务不可用时直接返回"""
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = None
        mock_us_cls.return_value = mock_us

        mock_get_ts.return_value = None

        with app.app_context():
            book = {'title': 'Test', 'description': 'Desc', 'details': 'Details'}
            merge_or_translate_book(book, '9780143127550')

            mock_submit.assert_not_called()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_no_fields_need_translation(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """所有字段已有中文翻译，无需翻译"""
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = None
        mock_us_cls.return_value = mock_us

        with app.app_context():
            book = {
                'title': 'Test',
                'title_zh': '已有书名',
                'description': 'Desc',
                'description_zh': '已有简介',
                'details': 'Details',
                'details_zh': '已有详情',
            }
            merge_or_translate_book(book, '9780143127550')

            mock_submit.assert_not_called()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_skips_no_summary_description(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """description 为 'No summary available.' 时不翻译"""
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = None
        mock_us_cls.return_value = mock_us

        mock_translation_service = MagicMock()
        mock_get_ts.return_value = mock_translation_service

        with app.app_context():
            book = {
                'title': 'Test',
                'title_zh': '已有书名',
                'description': 'No summary available.',
                'details': 'Details',
                'details_zh': '已有详情',
            }
            merge_or_translate_book(book, '9780143127550')

            mock_submit.assert_not_called()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_skips_no_detailed_description(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """details 为 'No detailed description available.' 时不翻译"""
        mock_us = MagicMock()
        mock_us.get_book_metadata.return_value = None
        mock_us_cls.return_value = mock_us

        mock_translation_service = MagicMock()
        mock_get_ts.return_value = mock_translation_service

        with app.app_context():
            book = {
                'title': 'Test',
                'title_zh': '已有书名',
                'description': 'Desc',
                'description_zh': '已有简介',
                'details': 'No detailed description available.',
            }
            merge_or_translate_book(book, '9780143127550')

            mock_submit.assert_not_called()

    @patch('app.services.book_detail_service.get_translation_service')
    @patch('app.services.book_detail_service.submit_background_task')
    @patch('app.services.book_detail_service.clean_translation_text')
    @patch('app.services.user_service.UserService')
    def test_user_service_exception_handled(self, mock_us_cls, mock_clean, mock_submit, mock_get_ts, app, db):
        """UserService 异常被安全捕获"""
        mock_us_cls.side_effect = RuntimeError('DB connection error')

        with app.app_context():
            book = {'title': 'Test'}
            merge_or_translate_book(book, '9780143127550')

            mock_submit.assert_not_called()
