"""
图书服务测试

测试 BookService 的核心功能，包括获取图书列表、搜索图书、保存翻译等
"""

import json
import os
from unittest.mock import Mock, patch

import pytest
from flask import has_app_context

from app.models.book import Book
from app.models.schemas import BookMetadata, SystemConfig, TranslationCache
from app.services.book_language_pack import BookLanguagePack
from app.services.book_service import BookService
from app.services.translation_cache_service import TranslationCacheService
from app.utils.exceptions import APIException


class TestBookService:
    """图书服务测试类"""

    @pytest.fixture
    def book_service(self, db):
        """创建图书服务实例"""
        # 模拟依赖服务
        nyt_client = Mock()
        google_client = Mock()
        cache_service = Mock()
        image_cache = Mock()

        # 配置模拟对象
        nyt_client.fetch_books.return_value = {
            'results': {
                'list_name': 'Hardcover Fiction',
                'published_date': '2024-01-14',
                'books': [
                    {
                        'primary_isbn13': '9780143127550',
                        'primary_isbn10': '014312755X',
                        'rank': 1,
                        'title': 'Test Book Title',
                        'author': 'Test Author',
                        'description': 'A compelling story.',
                        'book_image': 'https://example.com/image.jpg',
                        'publisher': 'Test Publisher',
                        'weeks_on_list': 10,
                        'rank_last_week': '2',
                        'price': '28.00',
                        'buy_links': [{'name': 'Amazon', 'url': 'https://amazon.com'}],
                    }
                ],
            }
        }

        google_client.fetch_book_details.return_value = {
            'isbn_13': '9780143127550',
            'isbn_10': '014312755X',
            'title': 'Test Book Title',
            'author': 'Test Author',
            'publisher': 'Test Publisher',
            'publication_dt': '2023-10-01',
            'page_count': 320,
            'language': 'eng',
            'details': 'Detailed book description from Google Books.',
            'cover_url': 'https://example.com/cover.jpg',
        }

        cache_service.get.return_value = None
        cache_service.get_stale.return_value = None
        cache_service.set.return_value = True
        cache_service.get_cache_time.return_value = '2024-01-14 12:00:00'

        image_cache.get_cached_image_url.return_value = 'https://example.com/cached_image.jpg'

        # 创建图书服务实例
        return BookService(
            nyt_client=nyt_client,
            google_client=google_client,
            cache_service=cache_service,
            image_cache=image_cache,
            categories={'hardcover-fiction': '精装小说'},
        )

    def test_get_books_by_category(self, book_service, db):
        """测试获取指定分类的图书列表"""
        # 执行测试
        books = book_service.get_books_by_category('hardcover-fiction', auto_translate=False)

        # 验证结果
        assert len(books) == 1
        assert isinstance(books[0], Book)
        assert books[0].title == 'Test Book Title'
        assert books[0].author == 'Test Author'
        assert books[0].isbn13 == '9780143127550'
        assert books[0].category_id == 'hardcover-fiction'

    def test_force_refresh_reaches_nyt_client(self, book_service):
        book_service.get_books_by_category('hardcover-fiction', force_refresh=True, auto_translate=False)

        book_service._nyt_client.fetch_books.assert_called_once_with('hardcover-fiction', force_refresh=True)

    @pytest.mark.parametrize('cache_state', ['fresh', 'stale'])
    @pytest.mark.parametrize('empty', [False, True])
    @pytest.mark.parametrize('force_refresh', [False, True])
    def test_cached_only_reads_existing_cache_without_refresh_work(
        self, book_service, mock_books_data, cache_state, empty, force_refresh
    ):
        """派生榜请求直接读缓存；真实空榜也不触发远端补全。"""
        rows = [] if empty else mock_books_data[:1]
        book_service._cache.get.return_value = rows if cache_state == 'fresh' else None
        book_service._cache.get_stale.return_value = rows
        with (
            patch.object(book_service, '_process_api_response') as process,
            patch.object(book_service, '_auto_translate_books') as translate,
            patch.object(book_service, '_notify_data_refreshed') as notify,
        ):
            books = book_service.get_books_by_category(
                'hardcover-fiction', cached_only=True, force_refresh=force_refresh
            )

        assert [book.title for book in books] == ([] if empty else [rows[0]['title']])
        book_service._nyt_client.fetch_books.assert_not_called()
        book_service._google_client.fetch_book_details.assert_not_called()
        book_service._cache.set.assert_not_called()
        process.assert_not_called()
        translate.assert_not_called()
        notify.assert_not_called()
        if cache_state == 'fresh':
            book_service._cache.get_stale.assert_not_called()
        else:
            book_service._cache.get_stale.assert_called_once_with('books_hardcover-fiction')

    @pytest.mark.parametrize('force_refresh', [False, True])
    def test_cached_only_missing_cache_reports_unavailable_without_remote_work(self, book_service, force_refresh):
        """缺失缓存须显式失败，不能伪装成已成功查出的零本。"""
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = None

        with (
            patch.object(book_service, '_auto_translate_books') as translate,
            patch.object(book_service, '_notify_data_refreshed') as notify,
            pytest.raises(APIException),
        ):
            book_service.get_books_by_category('hardcover-fiction', cached_only=True, force_refresh=force_refresh)

        book_service._nyt_client.fetch_books.assert_not_called()
        book_service._google_client.fetch_book_details.assert_not_called()
        book_service._cache.set.assert_not_called()
        translate.assert_not_called()
        notify.assert_not_called()

    def test_explicit_cached_only_false_preserves_network_refresh(self, book_service):
        books = book_service.get_books_by_category(
            'hardcover-fiction', cached_only=False, auto_translate=False, notify_refresh=False
        )

        assert len(books) == 1
        book_service._nyt_client.fetch_books.assert_called_once_with('hardcover-fiction', force_refresh=False)
        book_service._google_client.fetch_book_details.assert_called_once_with('9780143127550')
        book_service._cache.set.assert_called_once()

    def test_batch_get_supplements_keeps_app_context_in_workers(self, book_service, app):
        """Google Books 并发请求应在 Flask 应用上下文中执行。"""
        book_service._app = app

        def fetch_details(isbn):
            assert has_app_context()
            return {'isbn_13': isbn}

        book_service._google_client.fetch_book_details.side_effect = fetch_details

        with patch('app.services.book_service.log_error') as log_error:
            supplements = book_service._batch_get_supplements(['9780000000001', '9780000000002'])

        assert supplements == {
            '9780000000001': {'isbn_13': '9780000000001'},
            '9780000000002': {'isbn_13': '9780000000002'},
        }
        log_error.assert_not_called()

    def test_get_books_by_category_with_cache(self, book_service):
        """测试从缓存获取图书列表"""
        # 模拟缓存数据
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = cached_books

        # 执行测试
        books = book_service.get_books_by_category('hardcover-fiction')

        # 验证结果
        assert len(books) == 1
        assert books[0].title == 'Cached Book'
        assert books[0].author == 'Cached Author'

    def test_get_books_by_category_hydrates_cached_books_from_static_language_pack(self, book_service, tmp_path):
        """测试缓存图书会从静态语言包补齐中文字段"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        pack_path.write_text(
            json.dumps(
                {
                    'books': {
                        '9780143127550': {
                            'title_zh': '缓存书名',
                            'description_zh': '缓存简介',
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        book_service._language_pack = BookLanguagePack(pack_path)
        book_service._cache.get.return_value = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]

        books = book_service.get_books_by_category('hardcover-fiction')

        assert books[0].title_zh == '缓存书名'
        assert books[0].description_zh == '缓存简介'

    @pytest.mark.parametrize('translation_source', ['cached_book', 'metadata'])
    def test_language_pack_corrects_known_description_in_cached_service(
        self, book_service, db, tmp_path, translation_source
    ):
        """已知坏简介来自缓存对象或元数据时，都应在读取后定点纠正。"""
        isbn = '9780143127550'
        old_description = '《只有书名的错误简介》'
        corrected_description = '这是一段经人工核对的完整故事简介。'
        pack_path = tmp_path / 'book_language_pack.zh.json'
        pack_path.write_text(
            json.dumps(
                {
                    'books': {
                        isbn: {'description_zh': corrected_description, 'description_zh_replaces': [old_description]}
                    }
                }
            ),
            encoding='utf-8',
        )
        pack_before = pack_path.read_bytes()
        book_service._language_pack = BookLanguagePack(pack_path)
        source = book_service._nyt_client.fetch_books.return_value['results']['books'][0]
        cached_book = Book.from_api_response(
            source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {}
        )
        cached_book.title_zh = '已有正确书名'
        cached_book.details_zh = '已有正确详情'
        if translation_source == 'cached_book':
            cached_book.description_zh = old_description
        else:
            db.session.add(
                BookMetadata(isbn=isbn, title='Cached Book', author='Cached Author', description_zh=old_description)
            )
        db.session.commit()
        book_service._cache.get.return_value = [cached_book.to_dict()]

        with (
            patch.object(book_service, '_auto_translate_books') as translate,
            patch.object(db.session, 'commit') as commit,
        ):
            books = book_service.get_books_by_category('hardcover-fiction', auto_translate=False)

        assert books[0].description_zh == corrected_description
        assert books[0].title_zh == '已有正确书名'
        assert books[0].details_zh == '已有正确详情'
        translate.assert_not_called()
        commit.assert_not_called()
        book_service._nyt_client.fetch_books.assert_not_called()
        book_service._google_client.fetch_book_details.assert_not_called()
        assert pack_path.read_bytes() == pack_before
        if translation_source == 'metadata':
            assert db.session.get(BookMetadata, isbn).description_zh == old_description

    def test_background_translation_keeps_another_category_while_busy(self, book_service, tmp_path, mock_books_data):
        book_service._language_pack = BookLanguagePack(tmp_path / 'pack.json')
        first, second = [Book(**row) for row in mock_books_data]
        processed = []

        def translate(batch):
            processed.extend(book.isbn13 for book in batch)
            if first in batch:
                book_service._auto_translate_books([first, second, second])
            return {'books_seen': len(batch), 'fields_translated': len(batch), 'failures': 0, 'pack_writes': 1}

        with (
            patch('app.services.book_service.threading.Thread') as thread,
            patch.object(book_service, '_translate_books_now', side_effect=translate),
        ):
            book_service._auto_translate_books([first])
            thread.call_args.kwargs['target']()

        assert processed == [first.isbn13, second.isbn13]
        thread.assert_called_once()
        assert book_service._translation_thread_active is False

    def test_background_translation_reports_partial_failure(self, book_service, tmp_path, mock_books_data, caplog):
        book_service._language_pack = BookLanguagePack(tmp_path / 'pack.json')
        book = Book(**mock_books_data[0])
        stats = {'books_seen': 1, 'fields_translated': 1, 'failures': 2, 'pack_writes': 1}

        with (
            patch('app.services.book_service.threading.Thread') as thread,
            patch.object(book_service, '_translate_books_now', return_value=stats),
        ):
            book_service._auto_translate_books([book])
            thread.call_args.kwargs['target']()

        assert '失败字段2个' in caplog.text
        assert book.isbn13 in caplog.text
        assert '批量预翻译完成' not in caplog.text
        assert book_service._translation_thread_active is False

    def test_background_translation_continues_queue_after_exception(
        self, book_service, tmp_path, mock_books_data, caplog
    ):
        book_service._language_pack = BookLanguagePack(tmp_path / 'pack.json')
        first, second = [Book(**row) for row in mock_books_data]
        processed = []

        def translate(batch):
            processed.extend(book.isbn13 for book in batch)
            if first in batch:
                book_service._auto_translate_books([second])
                raise ValueError('test failure')
            return {'books_seen': 1, 'fields_translated': 1, 'failures': 0, 'pack_writes': 1}

        with (
            patch('app.services.book_service.threading.Thread') as thread,
            patch.object(book_service, '_translate_books_now', side_effect=translate),
        ):
            book_service._auto_translate_books([first])
            thread.call_args.kwargs['target']()

        assert processed == [first.isbn13, second.isbn13]
        assert first.isbn13 in caplog.text
        assert book_service._translation_thread_active is False

    def test_background_translation_can_retry_after_thread_start_failure(self, book_service, tmp_path, mock_books_data):
        book_service._language_pack = BookLanguagePack(tmp_path / 'pack.json')
        book = Book(**mock_books_data[0])
        stats = {'books_seen': 1, 'fields_translated': 2, 'failures': 0, 'pack_writes': 1}

        with (
            patch('app.services.book_service.threading.Thread') as thread,
            patch.object(book_service, '_translate_books_now', return_value=stats) as translate,
        ):
            thread.return_value.start.side_effect = RuntimeError('cannot start thread')
            book_service._auto_translate_books([book])
            assert book_service._translation_thread_active is False
            thread.return_value.start.side_effect = None
            book_service._auto_translate_books([book])
            thread.call_args.kwargs['target']()

        translate.assert_called_once_with([book])
        assert book_service._translation_thread_active is False

    def test_background_translation_bounds_pending_queue_and_allows_later_retry(
        self, book_service, tmp_path, mock_books_data, caplog
    ):
        book_service._language_pack = BookLanguagePack(tmp_path / 'pack.json')
        book_service._MAX_PENDING_TRANSLATION_BOOKS = 1
        first, second = [Book(**row) for row in mock_books_data]
        stats = {'books_seen': 1, 'fields_translated': 1, 'failures': 0, 'pack_writes': 1}

        with (
            patch('app.services.book_service.threading.Thread') as thread,
            patch.object(book_service, '_translate_books_now', return_value=stats) as translate,
        ):
            book_service._auto_translate_books([first, second])
            assert len(book_service._translation_pending) == 1
            thread.call_args.kwargs['target']()
            book_service._auto_translate_books([second])
            thread.call_args.kwargs['target']()

        assert [call.args[0] for call in translate.call_args_list] == [[first], [second]]
        assert '队列已满' in caplog.text

    def test_background_translation_failed_cache_request_can_recover(
        self, book_service, tmp_path, mock_books_data, monkeypatch
    ):
        monkeypatch.delenv('SPACE_ID', raising=False)
        pack_path = tmp_path / 'pack.json'
        book_service._language_pack = BookLanguagePack(pack_path)
        book_service._cache.get.return_value = [mock_books_data[0]]
        ready = False
        translator = Mock()
        translator.is_available.return_value = True
        translator.translate.side_effect = lambda *args, **kwargs: (
            {'title': '测试书名', 'description': '已恢复的中文简介', 'details': '中文详情'}[kwargs['field_type']]
            if ready
            else None
        )

        with (
            patch('app.services.book_service.threading.Thread') as thread,
            patch.object(book_service, '_get_translation_service', return_value=translator),
        ):
            first = book_service.get_books_by_category('hardcover-fiction')
            thread.call_args.kwargs['target']()
            assert not first[0].description_zh
            assert not pack_path.exists()

            ready = True
            second = book_service.get_books_by_category('hardcover-fiction')
            thread.call_args.kwargs['target']()
            assert second[0].description_zh == '已恢复的中文简介'
            third = book_service.get_books_by_category('hardcover-fiction')

        assert third[0].description_zh == '已恢复的中文简介'
        assert (
            json.loads(pack_path.read_text(encoding='utf-8'))['books'][first[0].isbn13]['description_zh']
            == '已恢复的中文简介'
        )
        assert thread.call_count == 2
        book_service._nyt_client.fetch_books.assert_not_called()

    @pytest.mark.parametrize(
        ('isbn', 'description_zh'),
        [
            ('9780143127550', '已有正确中文简介'),
            ('9780143127550', ' 《只有书名的错误简介》 '),
            ('9780000000002', '《只有书名的错误简介》'),
        ],
        ids=['valid-description', 'exact-match-required', 'different-isbn'],
    )
    def test_language_pack_description_correction_preserves_other_translations(
        self, db, tmp_path, isbn, description_zh
    ):
        pack_path = tmp_path / 'book_language_pack.zh.json'
        pack_path.write_text(
            json.dumps(
                {
                    'books': {
                        '9780143127550': {
                            'title_zh': '另一书名',
                            'description_zh': '经核对的完整简介。',
                            'details_zh': '另一详情',
                            'description_zh_replaces': ['《只有书名的错误简介》'],
                        }
                    }
                }
            ),
            encoding='utf-8',
        )
        book = {'isbn13': isbn, 'description_zh': description_zh, 'title_zh': '原书名', 'details_zh': '原详情'}

        BookLanguagePack(pack_path).hydrate_books([book])

        assert book == {
            'isbn13': isbn,
            'description_zh': description_zh,
            'title_zh': '原书名',
            'details_zh': '原详情',
        }

    @pytest.mark.parametrize('pack_change', ['replacement', 'removed', 'deleted', 'invalid_json', 'read_failure'])
    def test_language_pack_description_correction_reloads_and_discards_stale_rules(self, db, tmp_path, pack_change):
        isbn = '9780143127550'
        old_description = '已知错误简介'
        pack_path = tmp_path / 'book_language_pack.zh.json'
        document = {'books': {isbn: {'description_zh': '第一版正确简介', 'description_zh_replaces': [old_description]}}}
        pack_path.write_text(json.dumps(document), encoding='utf-8')
        language_pack = BookLanguagePack(pack_path)
        first_book = {'isbn13': isbn, 'description_zh': old_description}
        language_pack.hydrate_books([first_book])
        assert first_book['description_zh'] == '第一版正确简介'
        previous_stat = pack_path.stat()

        if pack_change == 'deleted':
            pack_path.unlink()
        else:
            if pack_change == 'replacement':
                document['books'][isbn]['description_zh'] = '第二版正确简介'
            elif pack_change == 'removed':
                document['books'][isbn].pop('description_zh_replaces')
            pack_path.write_text('{' if pack_change == 'invalid_json' else json.dumps(document), encoding='utf-8')
            os.utime(pack_path, ns=(previous_stat.st_atime_ns, previous_stat.st_mtime_ns + 1_000_000_000))

        next_book = {'isbn13': isbn, 'description_zh': old_description}
        if pack_change == 'read_failure':
            with patch.object(type(pack_path), 'read_text', side_effect=OSError('unreadable test pack')):
                language_pack.hydrate_books([next_book])
        else:
            language_pack.hydrate_books([next_book])

        assert next_book['description_zh'] == ('第二版正确简介' if pack_change == 'replacement' else old_description)

    @pytest.mark.parametrize('replaces', [None, '已知错误简介', {'old': '已知错误简介'}, [7], ['已知错误简介', 7], []])
    def test_language_pack_description_correction_ignores_invalid_rules(self, db, tmp_path, replaces):
        pack_path = tmp_path / 'book_language_pack.zh.json'
        pack_path.write_text(
            json.dumps(
                {'books': {'9780143127550': {'description_zh': '正确简介', 'description_zh_replaces': replaces}}}
            ),
            encoding='utf-8',
        )
        book = {'isbn13': '9780143127550', 'description_zh': '已知错误简介'}

        BookLanguagePack(pack_path).hydrate_books([book])

        assert book['description_zh'] == '已知错误简介'

    def test_get_books_by_category_hydrates_cached_books_from_translation_cache(self, book_service, db):
        """测试缓存图书会从翻译缓存补齐中文字段"""
        for source, translated in [('Cached Book', '缓存书名'), ('Test description', '缓存简介')]:
            db.session.add(
                TranslationCache(
                    source_hash=TranslationCacheService._compute_source_hash(source),
                    source_text=source,
                    source_lang='en',
                    target_lang='zh',
                    translated_text=translated,
                    model_name='test',
                )
            )
        db.session.commit()

        book_service._cache.get.return_value = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]

        books = book_service.get_books_by_category('hardcover-fiction')

        assert books[0].title_zh == '缓存书名'
        assert books[0].description_zh == '缓存简介'

    def test_language_pack_translates_and_writes_missing_fields(self, tmp_path):
        """测试语言包会翻译缺失字段并写回JSON文件"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book = Book(
            id='9780143127550',
            title='Test Book',
            author='Test Author',
            publisher='Test Publisher',
            cover='',
            list_name='Hardcover Fiction',
            category_id='hardcover-fiction',
            category_name='精装小说',
            rank=1,
            weeks_on_list=1,
            rank_last_week='0',
            published_date='2024-01-01',
            description='A test description',
            details='Detailed book description',
            publication_dt='2024-01-01',
            page_count='200',
            language='English',
            buy_links=[],
            isbn13='9780143127550',
            isbn10='0143127550',
            price='19.99',
        )

        class FakeTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                return {
                    'title': '测试书名',
                    'description': '测试简介',
                    'details': '测试详情',
                }[field_type]

        stats = BookLanguagePack(pack_path).translate_and_store_books([book], translator=FakeTranslator())

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert stats['fields_translated'] == 3
        assert saved['books']['9780143127550']['title_zh'] == '测试书名'
        assert saved['books']['9780143127550']['description_zh'] == '测试简介'
        assert saved['books']['9780143127550']['details_zh'] == '测试详情'
        assert book.title_zh == '测试书名'

    def test_language_pack_rejects_language_marker_details(self, tmp_path):
        """details_zh 是语言标记（'英文'）时不得写进权威语言包。

        回归：sync_book_language_pack.py 曾把上游 cache 里的「英文」合并进语言包
        （实测 88 条、其中 32 本在榜），页面渲染成「详情: 英文」。
        """
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book = {
            'id': '9780143127550',
            'isbn13': '9780143127550',
            'title': 'Test Book',
            'title_zh': '测试书名',
            'description': 'A test description',
            'description_zh': '测试简介',
            'details': 'Detailed book description',
            'details_zh': '英文',
        }

        stats = BookLanguagePack(pack_path).translate_and_store_books([book])

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        entry = saved['books']['9780143127550']
        assert 'details_zh' not in entry
        assert entry['title_zh'] == '测试书名'
        assert entry['description_zh'] == '测试简介'
        assert stats['rejected_non_substantive'] == 1
        assert stats['fields_stored'] == 2

    def test_language_pack_keeps_real_details_zh(self, tmp_path):
        """正常中文详情不得被噪音判定误伤。"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book = {
            'id': '9780143127550',
            'isbn13': '9780143127550',
            'title': 'Test Book',
            'details': 'Detailed book description',
            'details_zh': '最初由Viking Penguin于2014年出版。',
        }

        stats = BookLanguagePack(pack_path).translate_and_store_books([book])

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert saved['books']['9780143127550']['details_zh'] == '最初由Viking Penguin于2014年出版。'
        assert stats.get('rejected_non_substantive', 0) == 0

    def test_sync_all_categories_refreshes_metadata_and_language_pack(self, book_service, db, tmp_path):
        """测试每周NYT同步会补资料、翻译并写入语言包和数据库"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)

        class FakeTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                return {
                    'title': '测试书名',
                    'description': '测试简介',
                    'details': '测试详情',
                }[field_type]

        with patch.object(book_service, '_auto_translate_books') as auto_translate:
            results = book_service.sync_all_categories(translator=FakeTranslator())

        assert results == [
            {
                'category_id': 'hardcover-fiction',
                'category_name': '精装小说',
                'success': True,
                'books': 1,
                'metadata_saved': 1,
                'language_pack': {
                    'books_seen': 1,
                    'books_missing': 1,
                    'fields_from_pack': 0,
                    'fields_stored': 0,
                    'fields_translated': 3,
                    'failures': 0,
                    'pack_writes': 1,
                },
            }
        ]
        auto_translate.assert_not_called()

        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert saved['books']['9780143127550']['title_zh'] == '测试书名'
        assert saved['books']['9780143127550']['description_zh'] == '测试简介'
        assert saved['books']['9780143127550']['details_zh'] == '测试详情'

        metadata = db.session.get(BookMetadata, '9780143127550')
        assert metadata is not None
        assert metadata.title == 'Test Book Title'
        assert metadata.author == 'Test Author'
        assert metadata.details == 'Detailed book description from Google Books.'
        assert metadata.title_zh == '测试书名'
        assert metadata.description_zh == '测试简介'
        assert metadata.details_zh == '测试详情'

    def test_get_books_by_category_skips_side_effects_on_space(self, book_service, monkeypatch):
        """Space 唯一 worker 不得被首屏的后台预翻译和刷新回调占用。"""
        monkeypatch.setenv('SPACE_ID', 'Elvis85/bookrank')
        notified = []

        def callback():
            notified.append(1)

        book_service.on_data_refreshed(callback)

        with patch.object(book_service, '_auto_translate_books') as auto_translate:
            books = book_service.get_books_by_category('hardcover-fiction')

        assert len(books) == 1
        auto_translate.assert_not_called()
        assert notified == []

    def test_process_api_response_skips_batch_lookups_on_space(self, book_service, monkeypatch):
        """Space 上批量翻译/增补改为按需补齐，避免请求期内串行等待上游。"""
        monkeypatch.setenv('SPACE_ID', 'Elvis85/bookrank')

        with (
            patch.object(book_service, '_batch_get_translations') as translations,
            patch.object(book_service, '_batch_get_supplements') as supplements,
        ):
            book_service.get_books_by_category('hardcover-fiction')

        translations.assert_not_called()
        supplements.assert_not_called()

    def test_process_api_response_fetches_batch_lookups_off_space(self, book_service, monkeypatch):
        monkeypatch.delenv('SPACE_ID', raising=False)

        with (
            patch.object(book_service, '_batch_get_translations', return_value={}) as translations,
            patch.object(book_service, '_batch_get_supplements', return_value={}) as supplements,
        ):
            book_service.get_books_by_category('hardcover-fiction')

        translations.assert_called_once()
        supplements.assert_called_once()

    def test_get_books_by_category_returns_stale_cache_on_api_failure(self, book_service):
        """测试API失败时返回过期文件缓存"""
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = cached_books
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT unavailable')

        books = book_service.get_books_by_category('hardcover-fiction')

        assert len(books) == 1
        assert books[0].title == 'Cached Book'

    def test_strict_refresh_does_not_treat_stale_cache_as_success(self, book_service):
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = [{'title': 'Stale Book'}]
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT unavailable')

        with pytest.raises(APIException, match='NYT unavailable'):
            book_service.get_books_by_category(
                'hardcover-fiction',
                force_refresh=True,
                allow_stale_fallback=False,
            )

    def test_strict_refresh_rejects_empty_api_result(self, book_service):
        book_service._cache.get.return_value = None
        book_service._nyt_client.fetch_books.return_value = {
            'results': {'books': [], 'list_name': 'Hardcover Fiction', 'published_date': '2026-09-06'}
        }

        with pytest.raises(APIException, match='no books'):
            book_service.get_books_by_category(
                'hardcover-fiction',
                force_refresh=True,
                allow_stale_fallback=False,
            )

    def test_get_books_by_category_treats_error_payload_as_failure(self, book_service):
        """测试NYT错误缓存不会被当成空榜单写入缓存"""
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = cached_books
        book_service._nyt_client.fetch_books.return_value = {'error': 'rate_limit_exceeded'}

        books = book_service.get_books_by_category('hardcover-fiction')

        assert len(books) == 1
        assert books[0].title == 'Cached Book'
        book_service._cache.set.assert_not_called()

    def test_report_failures_raises_on_api_failure_without_stale(self, book_service):
        """report_failures=True 且 API 失败且无过期缓存时，必须上抛而非伪装成空。"""
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = None
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT down')

        with pytest.raises(APIException, match='NYT down'):
            book_service.get_books_by_category('hardcover-fiction', report_failures=True)

    def test_default_still_swallows_api_failure_without_stale(self, book_service):
        """默认 report_failures=False 保持旧行为：无过期缓存时 API 失败返回空列表。"""
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = None
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT down')

        books = book_service.get_books_by_category('hardcover-fiction')
        assert books == []

    def test_report_failures_preserves_stale_fallback(self, book_service):
        """report_failures=True 时有过期缓存仍返回缓存（降级优先于上抛）。"""
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = cached_books
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT down')

        books = book_service.get_books_by_category('hardcover-fiction', report_failures=True)

        assert len(books) == 1
        assert books[0].title == 'Cached Book'

    def test_report_failures_keeps_genuine_empty_success(self, book_service):
        """report_failures=True 时「成功但空」仍是空列表，不因空数据误判失败。"""
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = None
        book_service._nyt_client.fetch_books.return_value = {
            'results': {'books': [], 'list_name': 'Hardcover Fiction', 'published_date': '2026-09-06'}
        }

        books = book_service.get_books_by_category('hardcover-fiction', report_failures=True)
        assert books == []

    def test_report_failures_raises_on_error_payload_without_stale(self, book_service):
        """report_failures=True 时 NYT 错误载荷（非空数据）按失败处理并上抛。"""
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = None
        book_service._nyt_client.fetch_books.return_value = {'error': 'rate_limit_exceeded'}

        with pytest.raises(APIException, match='rate_limit_exceeded'):
            book_service.get_books_by_category('hardcover-fiction', report_failures=True)

    def test_report_failures_hydrates_stale_chinese_title_from_language_pack(self, book_service, tmp_path):
        """report_failures=True 走过期缓存降级时，中文字段仍经语言包批量补齐。"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        pack_path.write_text(
            json.dumps(
                {
                    'books': {
                        '9780143127550': {
                            'title_zh': '缓存书名',
                            'description_zh': '缓存简介',
                        }
                    }
                },
                ensure_ascii=False,
            ),
            encoding='utf-8',
        )
        book_service._language_pack = BookLanguagePack(pack_path)
        cached_books = [
            {
                'id': '9780143127550',
                'title': 'Cached Book',
                'author': 'Cached Author',
                'publisher': 'Test Publisher',
                'cover': '',
                'list_name': 'Test List',
                'category_id': 'hardcover-fiction',
                'category_name': 'Hardcover Fiction',
                'rank': 1,
                'weeks_on_list': 1,
                'rank_last_week': '0',
                'published_date': '2024-01-01',
                'description': 'Test description',
                'details': 'Test details',
                'publication_dt': '2024-01-01',
                'page_count': '200',
                'language': 'English',
                'buy_links': [],
                'isbn13': '9780143127550',
                'isbn10': '0143127550',
                'price': '19.99',
            }
        ]
        book_service._cache.get.return_value = None
        book_service._cache.get_stale.return_value = cached_books
        book_service._nyt_client.fetch_books.side_effect = APIException('NYT down')

        books = book_service.get_books_by_category('hardcover-fiction', report_failures=True)

        assert len(books) == 1
        assert books[0].title_zh == '缓存书名'
        assert books[0].description_zh == '缓存简介'

    def test_save_book_translation(self, book_service, db):
        """测试保存图书翻译"""
        # 执行测试
        result = book_service.save_book_translation(
            isbn='9780143127550', title_zh='测试书名', description_zh='测试描述', details_zh='测试详情'
        )

        # 验证结果
        assert result is True

        # 验证数据库中是否保存了翻译
        metadata = db.session.get(BookMetadata, '9780143127550')
        assert metadata is not None
        assert metadata.title_zh == '测试书名'
        assert metadata.description_zh == '测试描述'
        assert metadata.details_zh == '测试详情'

    def test_save_book_translation_invalid_isbn(self, book_service):
        """测试保存图书翻译时ISBN无效的情况"""
        # 执行测试
        result = book_service.save_book_translation(isbn='', title_zh='测试书名')

        # 验证结果
        assert result is False

    def test_search_books(self, book_service):
        """测试搜索图书"""
        # 执行测试
        with patch.object(book_service, 'get_books_by_category') as mock_get_books:
            # 模拟返回的图书数据
            mock_book = Mock()
            mock_book.title = 'Test Book Title'
            mock_book.author = 'Test Author'
            mock_get_books.return_value = [mock_book]

            # 执行搜索
            results = book_service.search_books('Test')

            # 验证结果
            assert len(results) == 1

    def test_search_books_no_results(self, book_service):
        """测试搜索图书无结果的情况"""
        # 执行测试
        with patch.object(book_service, 'get_books_by_category') as mock_get_books:
            # 模拟返回的图书数据
            mock_book = Mock()
            mock_book.title = 'Other Book Title'
            mock_book.author = 'Other Author'
            mock_get_books.return_value = [mock_book]

            # 执行搜索
            results = book_service.search_books('Test')

            # 验证结果
            assert len(results) == 0

    def test_get_latest_cache_time(self, book_service):
        """测试获取最新缓存时间"""
        # 执行测试
        cache_time = book_service.get_latest_cache_time()

        # 验证结果
        assert cache_time == '2024-01-14 12:00:00'

    def test_get_latest_cache_time_no_data(self, book_service):
        """测试获取最新缓存时间时无数据的情况"""
        # 模拟缓存时间为None
        book_service._cache.get_cache_time.return_value = None

        # 执行测试
        cache_time = book_service.get_latest_cache_time()

        # 验证结果
        assert cache_time == '暂无数据'

    def test_save_book_metadata_batch_uses_single_select(self, book_service, db, app):
        """测试批量保存元数据只发起一次 SELECT 查询（避免 N+1）"""
        from sqlalchemy import event

        books = [
            Book(
                id='9780000001001',
                title=f'Batch Book {i}',
                author=f'Author {i}',
                publisher='Publisher',
                cover='',
                list_name='Test',
                category_id='hardcover-fiction',
                category_name='精装小说',
                rank=i,
                weeks_on_list=1,
                rank_last_week='0',
                published_date='2024-01-01',
                description='desc',
                details='details',
                publication_dt='2024-01-01',
                page_count='200',
                language='English',
                buy_links=[],
                isbn13=f'978000000100{i}',
                isbn10=f'000000100{i}',
                price='19.99',
            )
            for i in range(1, 6)
        ]

        select_count = 0

        def _count_selects(conn, cursor, statement, parameters, context, executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith('SELECT'):
                select_count += 1

        with app.app_context():
            event.listen(db.engine, 'before_cursor_execute', _count_selects)
            try:
                saved = book_service.save_book_metadata_batch(books)
            finally:
                event.remove(db.engine, 'before_cursor_execute', _count_selects)

        assert saved == 5
        assert select_count == 1  # 一次 IN 查询

    def test_save_book_metadata_loop_uses_multiple_selects(self, book_service, db, app):
        """测试逐条保存元数据会产生多次 SELECT 查询（对照组，说明 N+1）"""
        from sqlalchemy import event

        books = [
            Book(
                id='9780000002001',
                title=f'Loop Book {i}',
                author=f'Author {i}',
                publisher='Publisher',
                cover='',
                list_name='Test',
                category_id='hardcover-fiction',
                category_name='精装小说',
                rank=i,
                weeks_on_list=1,
                rank_last_week='0',
                published_date='2024-01-01',
                description='desc',
                details='details',
                publication_dt='2024-01-01',
                page_count='200',
                language='English',
                buy_links=[],
                isbn13=f'978000000200{i}',
                isbn10=f'000000200{i}',
                price='19.99',
            )
            for i in range(1, 6)
        ]

        select_count = 0

        def _count_selects(conn, cursor, statement, parameters, context, executemany):
            nonlocal select_count
            if statement.lstrip().upper().startswith('SELECT'):
                select_count += 1

        with app.app_context():
            event.listen(db.engine, 'before_cursor_execute', _count_selects)
            try:
                for book in books:
                    book_service.save_book_metadata(book)
            finally:
                event.remove(db.engine, 'before_cursor_execute', _count_selects)

        assert select_count == 5  # 每本书一次 SELECT

    @pytest.mark.parametrize(
        ('isbn', 'title', 'description'),
        [
            (
                '9781668251065',
                'PECK & PECK',
                'In 1982, a recent college graduate named Batter Gray winds up in the middle of '
                'internecine wars at a prestigious poetry journal.',
            ),
            (
                '9781464244698',
                'HEXED',
                'The sixth book in the Never After series. A forbidden love develops between '
                "the underboss to a mafia syndicate and his fiancee's cousin.",
            ),
            (
                '9781464244681',
                'CROSSED',
                'The fifth book in the Never After series. Father Cade becomes a priest in '
                'a Vermont town, where he is tempted by Amaya.',
            ),
        ],
        ids=['peck-peck', 'hexed', 'crossed'],
    )
    def test_cached_books_retry_missing_translations(
        self, book_service, db, tmp_path, monkeypatch, isbn, title, description
    ):
        """首次翻译失败后，缓存命中的新上榜图书仍应补译并持久化。"""
        monkeypatch.delenv('SPACE_ID', raising=False)
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)
        source = dict(book_service._nyt_client.fetch_books.return_value['results']['books'][0])
        source.update(primary_isbn13=isbn, primary_isbn10='', title=title, description=description)
        cached_book = Book.from_api_response(
            source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {}
        )
        book_service._cache.get.return_value = [cached_book.to_dict()]

        class FakeTranslator:
            def translate(self, text, source_lang='en', target_lang='zh', field_type='text'):
                return {'title': '测试书名', 'description': '测试中文简介'}[field_type]

        def translate_now(books):
            book_service._translate_books_now(books, translator=FakeTranslator())

        with patch.object(book_service, '_auto_translate_books', side_effect=translate_now) as auto_translate:
            books = book_service.get_books_by_category('hardcover-fiction')

        assert books[0].description_zh == '测试中文简介'
        auto_translate.assert_called_once()
        book_service._nyt_client.fetch_books.assert_not_called()
        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert saved['books'][isbn]['description_zh'] == '测试中文简介'
        metadata = db.session.get(BookMetadata, isbn)
        assert metadata is not None
        assert metadata.title_zh == '测试书名'
        assert metadata.description_zh == '测试中文简介'

    @pytest.mark.parametrize('skip_reason', ['disabled', 'space', 'already_translated'])
    def test_cached_books_skip_unnecessary_translation(self, book_service, monkeypatch, skip_reason):
        """缓存补译应遵守显式开关、Space 限制和已有中文字段。"""
        monkeypatch.delenv('SPACE_ID', raising=False)
        if skip_reason == 'space':
            monkeypatch.setenv('SPACE_ID', 'Elvis85/bookrank')
        source = book_service._nyt_client.fetch_books.return_value['results']['books'][0]
        cached_book = Book.from_api_response(
            source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {}
        )
        if skip_reason == 'already_translated':
            cached_book.title_zh = '测试书名'
            cached_book.description_zh = '测试中文简介'
        book_service._cache.get.return_value = [cached_book.to_dict()]

        with patch.object(book_service, '_auto_translate_books') as auto_translate:
            books = book_service.get_books_by_category('hardcover-fiction', auto_translate=skip_reason != 'disabled')

        assert len(books) == 1
        auto_translate.assert_not_called()
        book_service._nyt_client.fetch_books.assert_not_called()

    @pytest.mark.parametrize('description_zh', [None, '暂无简介'])
    def test_translate_books_now_counts_missing_fields_when_unavailable(self, book_service, tmp_path, description_zh):
        """翻译器不可用时，缺失简介应计为失败，已有译文及占位详情不计入。"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)
        source = book_service._nyt_client.fetch_books.return_value['results']['books'][0]
        book = Book.from_api_response(source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {})
        book.title_zh = '测试书名'
        book.description_zh = description_zh
        book.details = 'No detailed description available.'
        translator = Mock()
        translator.is_available.return_value = False

        stats = book_service._translate_books_now([book], translator=translator)

        assert stats == {
            'books_seen': 1,
            'books_missing': 1,
            'fields_from_pack': 0,
            'fields_stored': 0,
            'fields_translated': 0,
            'failures': 1,
            'pack_writes': 0,
        }
        translator.translate.assert_not_called()
        assert not pack_path.exists()

    @pytest.mark.parametrize('translation_source', ['existing', 'static_pack', 'static_pack_placeholder'])
    def test_translate_books_now_accepts_complete_books_when_unavailable(
        self, book_service, tmp_path, translation_source
    ):
        """已有中文或可从语言包补齐时，供应商不可用不应误报翻译失败。"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)
        source = book_service._nyt_client.fetch_books.return_value['results']['books'][0]
        book = Book.from_api_response(source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {})
        translations = {'title_zh': '测试书名', 'description_zh': '测试简介'}
        if translation_source == 'existing':
            book.title_zh = translations['title_zh']
            book.description_zh = translations['description_zh']
        else:
            pack_path.write_text(json.dumps({'books': {book.isbn13: translations}}), encoding='utf-8')
            if translation_source == 'static_pack_placeholder':
                book.description_zh = '暂无简介'
        translator = Mock()
        translator.is_available.return_value = False

        stats = book_service._translate_books_now([book], translator=translator)

        assert stats['books_missing'] == 0
        assert stats['failures'] == 0
        assert stats['pack_writes'] == 0
        assert book.title_zh == '测试书名'
        assert book.description_zh == '测试简介'
        translator.translate.assert_not_called()

    @pytest.mark.parametrize('stored_placeholder_source', ['metadata', 'static_pack'])
    def test_translate_books_now_counts_stored_placeholders_when_unavailable(
        self, book_service, db, tmp_path, stored_placeholder_source
    ):
        """补齐阶段读回的历史中文占位串也不能伪装成已译简介。"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)
        source = book_service._nyt_client.fetch_books.return_value['results']['books'][0]
        book = Book.from_api_response(source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {})
        book.title_zh = '测试书名'
        if stored_placeholder_source == 'metadata':
            db.session.add(
                BookMetadata(isbn=book.isbn13, title=book.title, author=book.author, description_zh='暂无简介')
            )
            db.session.commit()
        else:
            pack_path.write_text(json.dumps({'books': {book.isbn13: {'description_zh': '暂无简介'}}}), encoding='utf-8')
        translator = Mock()
        translator.is_available.return_value = False

        stats = book_service._translate_books_now([book], translator=translator)

        assert stats['books_missing'] == 1
        assert stats['failures'] == 1
        assert stats['pack_writes'] == 0
        translator.translate.assert_not_called()

    @pytest.mark.parametrize('translation_source', ['model', 'static_pack'])
    def test_translate_books_now_replaces_placeholder_with_available_translator(
        self, book_service, tmp_path, translation_source
    ):
        """供应商可用时，中文占位串仍须由既有语言包或真实翻译结果替换。"""
        pack_path = tmp_path / 'book_language_pack.zh.json'
        book_service._language_pack = BookLanguagePack(pack_path)
        source = book_service._nyt_client.fetch_books.return_value['results']['books'][0]
        book = Book.from_api_response(source, 'hardcover-fiction', '精装小说', 'Hardcover Fiction', '2026-10-25', {})
        book.title_zh = '测试书名'
        book.description_zh = '暂无简介'
        if translation_source == 'static_pack':
            pack_path.write_text(json.dumps({'books': {book.isbn13: {'description_zh': '测试简介'}}}), encoding='utf-8')
        translator = Mock()
        translator.is_available.return_value = True
        translator.translate.return_value = '测试简介'

        stats = book_service._translate_books_now([book], translator=translator)

        assert book.description_zh == '测试简介'
        assert stats['failures'] == 0
        assert stats['fields_translated'] == (1 if translation_source == 'model' else 0)
        if translation_source == 'model':
            translator.translate.assert_called_once()
        else:
            translator.translate.assert_not_called()
        saved = json.loads(pack_path.read_text(encoding='utf-8'))
        assert saved['books'][book.isbn13]['description_zh'] == '测试简介'

    @pytest.mark.parametrize(
        ('failure_mode', 'expected_failures'), [('unavailable', 2), ('all_fields', 2), ('description', 1)]
    )
    def test_sync_all_categories_reports_translation_failure(
        self, book_service, tmp_path, failure_mode, expected_failures
    ):
        """缺译或供应商返回空值时，同步仍保留英文资料，但分类不得报告完整成功。"""
        book_service._language_pack = BookLanguagePack(tmp_path / 'book_language_pack.zh.json')
        book_service._google_client.fetch_book_details.return_value = {}
        translator = Mock()
        translator.is_available.return_value = failure_mode != 'unavailable'
        translator.translate.side_effect = lambda text, *args, field_type='text', **kwargs: (
            '测试书名' if failure_mode == 'description' and field_type == 'title' else None
        )

        results = book_service.sync_all_categories(translator=translator)

        assert results[0]['language_pack']['failures'] == expected_failures
        assert results[0]['language_pack']['books_missing'] == 1
        assert results[0]['success'] is False
        assert results[0]['books'] == 1
        assert results[0]['metadata_saved'] == 1

    def test_sync_all_categories_without_translation_remains_successful(self, book_service):
        """显式关闭翻译仍表示仅同步英文资料，不受翻译器状态影响。"""
        translator = Mock()
        translator.is_available.return_value = False

        results = book_service.sync_all_categories(translate=False, translator=translator)

        assert results[0]['success'] is True
        assert results[0]['language_pack']['failures'] == 0
        translator.is_available.assert_not_called()
        translator.translate.assert_not_called()

    def test_nyt_sync_translation_failure_does_not_advance_success_time(
        self, book_service, app, db, tmp_path, monkeypatch
    ):
        """真实同步链翻译失败后，调度器不得启动七天成功冷却。"""
        from app.setup import _nyt_ranking_sync_task

        book_service._language_pack = BookLanguagePack(tmp_path / 'book_language_pack.zh.json')
        translator = Mock()
        translator.is_available.return_value = True
        translator.translate.return_value = None
        monkeypatch.setitem(app.extensions, 'book_service', book_service)
        monkeypatch.setitem(app.extensions, 'translation_service', translator)
        assert SystemConfig.get_value('last_nyt_ranking_sync_time') is None

        _nyt_ranking_sync_task(app)

        assert SystemConfig.get_value('last_nyt_ranking_sync_time') is None


def test_nyt_ranking_sync_task_refreshes_all_categories(app, db):
    """测试后台NYT任务会触发全分类刷新和语言包写入"""
    from app.setup import _nyt_ranking_sync_task

    book_service = Mock()
    translator = Mock()
    book_service.sync_all_categories.return_value = [
        {
            'success': True,
            'books': 2,
            'metadata_saved': 2,
            'language_pack': {'fields_translated': 4},
        }
    ]
    original_book_service = app.extensions.get('book_service')
    original_translation_service = app.extensions.get('translation_service')

    try:
        app.extensions['book_service'] = book_service
        app.extensions['translation_service'] = translator

        with app.app_context():
            _nyt_ranking_sync_task(app)

            book_service.sync_all_categories.assert_called_once_with(
                force_refresh=True,
                translate=True,
                translator=translator,
            )
            assert SystemConfig.get_value('last_nyt_ranking_sync_time') is not None
    finally:
        if original_book_service is not None:
            app.extensions['book_service'] = original_book_service
        else:
            app.extensions.pop('book_service', None)
        if original_translation_service is not None:
            app.extensions['translation_service'] = original_translation_service
        else:
            app.extensions.pop('translation_service', None)
